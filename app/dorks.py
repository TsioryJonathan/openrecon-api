from urllib.parse import quote


DORK_TEMPLATES: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "Social Media",
        "Profiles on social platforms, people-search, and forums.",
        [
            ("Instagram profile", 'site:instagram.com "{target}"'),
            ("Twitter / X profile", 'site:twitter.com "{target}"'),
            ("Facebook profile", 'site:facebook.com "{target}"'),
            ("LinkedIn profile", 'site:linkedin.com/in/ "{target}"'),
            ("Reddit user", 'site:reddit.com/user/ "{target}"'),
            ("TikTok profile", 'site:tiktok.com "@{target}"'),
            ("Discord mentions", 'site:discord.com "{target}"'),
            ("GitHub profile", 'site:github.com "{target}"'),
        ],
    ),
    (
        "Documents & Files",
        "Public documents, PDFs, spreadsheets mentioning the target.",
        [
            ("PDF documents", 'filetype:pdf "{target}"'),
            ("Word documents", 'filetype:doc "{target}"'),
            ("Word documents v2", 'filetype:docx "{target}"'),
            ("Spreadsheets", 'filetype:xls "{target}"'),
            ("Presentations", 'filetype:ppt "{target}"'),
            ("Plain text", 'filetype:txt "{target}"'),
            ("Compressed archives", 'filetype:zip OR filetype:rar "{target}"'),
            ("Resume / CV", 'filetype:pdf "{target}" "resume" OR "CV"'),
        ],
    ),
    (
        "Developer & Code",
        "Code repositories, gists, and paste sites.",
        [
            ("Git repositories", 'site:github.com "{target}"'),
            ("Code gists", 'site:gist.github.com "{target}"'),
            ("Paste sites", 'site:pastebin.com "{target}"'),
            ("Developer forums", 'site:stackoverflow.com "{target}"'),
        ],
    ),
    (
        "Forums & Communities",
        "Forum activity and community discussions.",
        [
            ("Reddit mentions", 'site:reddit.com "{target}"'),
            ("Quora mentions", 'site:quora.com "{target}"'),
            ("Hacker News", 'site:news.ycombinator.com "{target}"'),
            ("General forums", 'intext:"{target}" "forum"'),
        ],
    ),
    (
        "Credentials & Data Leaks",
        "Potentially leaked credentials or sensitive data.",
        [
            ("Leaked creds in paste", 'site:pastebin.com "{target}" "password"'),
            ("Leaked creds in github", 'site:github.com "{target}" "password"'),
            ("Email leaks", '"{target}" "email" "password" filetype:txt'),
            ("Index of directories", 'intitle:"index of" "{target}"'),
        ],
    ),
    (
        "Exposure & Devices",
        "Public-facing devices, webcams, and exposed services.",
        [
            ("Live webcams", 'inurl:"/{target}/" intitle:"live view"'),
            ("Exposed admin panels", 'inurl:admin intitle:"{target}"'),
            ("Public cloud buckets", 'site:s3.amazonaws.com "{target}"'),
        ],
    ),
    (
        "General Search",
        "Broad mentions of the target across the web.",
        [
            ("Exact username", '"{target}"'),
            ("In URL", 'inurl:"{target}"'),
            ("In title", 'intitle:"{target}"'),
        ],
    ),
]


def generate_dorks(target: str) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    result = []
    for name, desc, items in DORK_TEMPLATES:
        dorks = []
        for title, query_template in items:
            query = query_template.format(target=target)
            url = f"https://www.google.com/search?q={quote(query)}"
            dorks.append((title, query, url))
        result.append((name, desc, dorks))
    return result
