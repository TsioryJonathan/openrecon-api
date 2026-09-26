import asyncio
import ipaddress
import re
from typing import Any, cast

import httpx


def is_ip(query: str) -> bool:
    try:
        ipaddress.ip_address(query)
        return True
    except ValueError:
        return False


def _is_valid_domain(query: str) -> bool:
    domain_re = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})+(?<!-)$")
    return bool(domain_re.match(query))


async def recon_ip(ip: str) -> dict:
    url = (
        f"http://ip-api.com/json/{ip}"
        f"?fields=status,message,country,countryCode,regionName,city,lat,lon,"
        f"isp,org,as,asname,proxy,hosting,mobile"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") == "fail":
        return {"error": data.get("message", "IP lookup failed")}

    return {
        "country": data.get("country"),
        "country_code": data.get("countryCode"),
        "region": data.get("regionName"),
        "city": data.get("city"),
        "coordinates": {"lat": data.get("lat"), "lon": data.get("lon")},
        "isp": data.get("isp"),
        "organization": data.get("org"),
        "asn": data.get("as"),
        "as_name": data.get("asname"),
        "proxy": data.get("proxy"),
        "hosting": data.get("hosting"),
        "mobile": data.get("mobile"),
    }


async def _rdap(domain: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://rdap.org/domain/{domain}")
        if resp.status_code != 200:
            return {}
        data = resp.json()

    events = {e["eventAction"]: e["eventDate"] for e in data.get("events", [])}
    nameservers = [ns.get("ldhName", "") for ns in data.get("nameservers", [])]

    registrar = None
    for entity in data.get("entities", []):
        roles = entity.get("roles", [])
        if "registrar" in roles:
            vcard = entity.get("vcardArray", [])
            if len(vcard) > 1:
                for field in vcard[1]:
                    if field[0] == "fn":
                        registrar = field[3]
            break

    return {
        "registrar": registrar,
        "status": data.get("status", []),
        "created": events.get("registration"),
        "expires": events.get("expiration"),
        "nameservers": nameservers,
    }


async def _crt_sh(domain: str) -> list[str]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"https://crt.sh/?q=%25.{domain}&output=json")
        if resp.status_code != 200:
            return []
        try:
            entries = resp.json()
        except ValueError, KeyError:  # fix: was `except ValueError, KeyError`
            return []

    names = set()
    for e in entries:
        for name in str(e.get("name_value", "")).split("\n"):
            name = name.strip().lstrip("*.")
            if name and name not in (domain, f"www.{domain}"):
                names.add(name)
    return sorted(names)[:50]


async def _dns(domain: str, rtype: str) -> list[str]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://dns.google/resolve?name={domain}&type={rtype}")
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [a.get("data") or a.get("name", "") for a in data.get("Answer", [])]


async def recon_domain(domain: str) -> dict:
    rdap_fut = _rdap(domain)
    crt_fut = _crt_sh(domain)
    ns_fut = _dns(domain, "NS")
    mx_fut = _dns(domain, "MX")
    a_fut = _dns(domain, "A")
    txt_fut = _dns(domain, "TXT")
    cname_fut = _dns(domain, "CNAME")

    rdap, subdomains, ns, mx, a, txt, cname = await asyncio.gather(
        rdap_fut, crt_fut, ns_fut, mx_fut, a_fut, txt_fut, cname_fut
    )
    # gather unifies the mixed dict/list results to a common supertype
    rdap = cast(dict[str, Any], rdap)

    return {
        "registrar": rdap.get("registrar"),
        "created": rdap.get("created"),
        "expires": rdap.get("expires"),
        "status": rdap.get("status", []),
        "nameservers": rdap.get("nameservers", []),
        "subdomains": subdomains,
        "dns": {
            "NS": ns,
            "MX": mx,
            "A": a,
            "TXT": txt,
            "CNAME": cname,
        },
    }


async def recon(query: str) -> tuple[str, dict]:
    query = query.strip().lower()
    if is_ip(query):
        return "ip", await recon_ip(query)
    if _is_valid_domain(query):
        return "domain", await recon_domain(query)
    raise ValueError("Query must be an IP address or a valid domain")
