def parse_sherlock_file(raw_output: str) -> list[dict]:
    results = []

    for line in raw_output.splitlines():
        line = line.strip()

        if not line or line.startswith("Total Websites"):
            continue

        if not line.startswith("[+]"):
            continue

        splitted = line.split(": ", 1)
        domain = splitted[0].split(" ", 1)[1]
        results.append(
            {
                "domain": domain,
                "url": splitted[1],
            }
        )

    return results
