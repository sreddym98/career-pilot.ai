# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Conservative required-skill extraction from a job title + description.

The autopilot matcher intersects `jobs.required_skills` with the seeker's
skills (case-insensitively), so canonical names here match how people write
them on a profile ("API Testing", "CI/CD", "Selenium").

Rules: a skill is emitted only when the text literally mentions it (or a
well-known alias). Nothing is inferred. Ambiguous short words (REST, Go, Rust)
are matched case-sensitively or only in an unambiguous phrase.
"""
import re

# (canonical name, regex, case_sensitive)
_V = [
    ("Selenium", r"\bselenium\b", False),
    ("Cypress", r"\bcypress\b", False),
    ("Playwright", r"\bplaywright\b", False),
    ("Appium", r"\bappium\b", False),
    ("Tricentis Tosca", r"\btosca\b", False),
    ("Katalon", r"\bkatalon\b", False),
    ("WebdriverIO", r"\bwebdriver\s?io\b|\bwdio\b", False),
    ("Robot Framework", r"\brobot framework\b", False),
    ("Cucumber", r"\bcucumber\b", False),
    ("BDD", r"\bBDD\b|\bbehou?r[- ]driven\b", True),
    ("TestNG", r"\btestng\b", False),
    ("JUnit", r"\bjunit\b", False),
    ("pytest", r"\bpytest\b", False),
    ("Mocha", r"\bmocha\b", True),
    ("Jest", r"\bjest\b", True),
    ("Java", r"\bjava\b", False),
    ("Python", r"\bpython\b", False),
    ("JavaScript", r"\bjavascript\b|\bnode\.?js\b", False),
    ("TypeScript", r"\btypescript\b", False),
    ("C#", r"(?<![\w#])c#(?!\w)|\.net\b", False),
    ("Kotlin", r"\bkotlin\b", False),
    ("Groovy", r"\bgroovy\b", False),
    ("SQL", r"\bsql\b|\bpl/sql\b|\bt-sql\b", False),
    ("Postman", r"\bpostman\b", False),
    ("REST", r"\bREST\b|\brestful\b|\brest apis?\b", True),
    ("RestAssured", r"\b(?i:restassured|rest-assured)\b|\bREST Assured\b", True),
    ("API Testing", r"\bapi (test(ing|s)?|automation)\b|\btest(ing)? (of )?apis?\b|\bapi[- ]level test", False),
    ("GraphQL", r"\bgraphql\b", False),
    ("SoapUI", r"\bsoap ?ui\b", False),
    ("JMeter", r"\bjmeter\b", False),
    ("k6", r"\bk6\b", False),
    ("Gatling", r"\bgatling\b", False),
    ("LoadRunner", r"\bload ?runner\b", False),
    ("Performance Testing", r"\bperformance (test(ing)?|engineering)\b|\bload test(ing)?\b", False),
    ("CI/CD", r"\bci\s?/\s?cd\b|\bci-cd\b|\bcontinuous integration\b", False),
    ("Jenkins", r"\bjenkins\b", False),
    ("GitHub Actions", r"\bgithub actions\b", False),
    ("Azure DevOps", r"\bazure devops\b|\bado pipelines?\b", False),
    ("GitLab CI", r"\bgitlab[- ]ci\b", False),
    ("Git", r"\bgit\b", False),
    ("Docker", r"\bdocker\b", False),
    ("Kubernetes", r"\bkubernetes\b|\bk8s\b", False),
    ("AWS", r"\baws\b|\bamazon web services\b", False),
    ("Azure", r"\bazure\b", False),
    ("GCP", r"\bgcp\b|\bgoogle cloud\b", False),
    ("Terraform", r"\bterraform\b", False),
    ("Jira", r"\bjira\b", False),
    ("TestRail", r"\btestrail\b", False),
    ("Agile", r"\bagile\b|\bscrum\b", False),
    ("Manual Testing", r"\bmanual test(ing)?\b", False),
    ("Test Automation", r"\btest automation\b|\bautomation (test(ing)?|framework)s?\b|\bautomated test(ing|s)?\b", False),
    ("Regression Testing", r"\bregression test(ing)?\b", False),
    ("ETL Testing", r"\betl test(ing|er)?\b|\bdata warehouse test(ing)?\b", False),
    ("PySpark", r"\bpyspark\b", False),
    ("Spark", r"\bapache spark\b|\bspark\b", True),
    ("Redshift", r"\bredshift\b", False),
    ("Snowflake", r"\bsnowflake\b", False),
    ("Databricks", r"\bdatabricks\b", False),
    ("Airflow", r"\bairflow\b", False),
    ("Kafka", r"\bkafka\b", False),
    ("MongoDB", r"\bmongo(db)?\b", False),
    ("PostgreSQL", r"\bpostgres(ql)?\b", False),
    ("Oracle", r"\boracle\b", False),
    ("Salesforce", r"\bsalesforce\b", False),
    ("PEGA", r"\bpega\b", False),
    ("SAP", r"\bSAP\b", True),
    ("Burp Suite", r"\bburp( suite)?\b", False),
    ("Security Testing", r"\bsecurity test(ing)?\b|\bpenetration test(ing)?\b|\bowasp\b", False),
    ("Accessibility Testing", r"\baccessibility test(ing)?\b|\bwcag\b", False),
    ("Mobile Testing", r"\bmobile test(ing)?\b|\bios and android\b", False),
    ("Contract Testing", r"\bpact\b|\bcontract test(ing)?\b", True),
    ("React", r"\breact(\.?js)?\b", False),
    ("Angular", r"\bangular(js)?\b", False),
    ("Linux", r"\blinux\b", False),
    ("Bash", r"\bbash\b|\bshell script(ing)?\b", False),
    ("HL7/FHIR", r"\bhl7\b|\bfhir\b", False),
    ("PCI-DSS", r"\bpci[- ]dss\b", False),
]

_COMPILED = [(name, re.compile(pat, 0 if cs else re.I)) for name, pat, cs in _V]
MAX_SKILLS = 25


def extract_skills(title: str = "", description: str = "") -> list[str]:
    """Skills literally mentioned in the text, in vocabulary order."""
    text = f"{title or ''}\n{(description or '')[:20000]}"
    if not text.strip():
        return []
    out = [name for name, rx in _COMPILED if rx.search(text)]
    return out[:MAX_SKILLS]
