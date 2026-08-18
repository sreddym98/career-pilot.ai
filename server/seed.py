# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""One-command bootstrap: creates tables and loads realistic sample data.

    python seed.py
"""
import datetime as dt, os, sys, hashlib
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL", "sqlite:///./dev.db")

from api.db import init_db, SessionLocal
from api.models import User, Position, UserSkill, Job, Course, Connection, Referral
from ingest.visa_parse import parse_visa

TAXONOMY_SAMPLE = {
    "ui": "Quality", "etl": "Quality", "api": "Quality", "perf": "Quality",
    "pega": "Quality", "aiq": "Quality", "hcit": "Healthcare", "sre": "Infrastructure",
}


def fingerprint(co, title, loc):
    key = f"{co.lower()}|{title.lower()}|{(loc or '').lower()}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


JOBS = [
 ("Mastercard","Senior SDET — Payment Processing","O'Fallon, MO","hybrid","fulltime","ui",145000,175000,"yr",5,10,True,"employer",
  "Playwright and Selenium automation for payment platforms. PCI-DSS compliance testing. We sponsor H1B transfers.",
  "https://careers.mastercard.com",["Playwright","Selenium","Tosca","PCI-DSS"],2,1),
 ("UnitedHealth Group","ETL Test Engineer — Claims Data","Remote","remote","fulltime","etl",120000,150000,"yr",5,9,True,"employer",
  "PySpark and Redshift validation across claims pipelines. HL7/FHIR knowledge a plus.",
  "https://careers.unitedhealthgroup.com",["PySpark","Redshift","SQL","HL7/FHIR"],1,1),
 ("Net2Source Inc","QE / SDET — POS & Merchandising","Camp Hill, PA","onsite","contract","ui",60,65,"hr",5,10,False,"staffing",
  "Our client is seeking an Oracle XStore POS tester. Rate: $60-65/hr on C2C. Visa: USC, GC, H1B.",
  "",["Oracle XStore","Selenium","Appium"],3,4),
 ("Bank of America","Quality Engineer — Payments API","Charlotte, NC","hybrid","fulltime","api",110000,138000,"yr",5,10,True,"employer",
  "RestAssured and Postman API validation. Candidates must be authorized to work in the US without sponsorship.",
  "https://careers.bankofamerica.com",["RestAssured","Postman","OAuth 2.0"],11,1),
 ("Ampstek","Automation Testing — PEGA","Bloomfield, CT","onsite","contract","pega",53,53,"hr",5,10,False,"staffing",
  "NOTE: ONLY H1B. Rate $53/hr C2C. PEGA functional and automation testing for our client Infosys.",
  "",["PEGA","REST API","CI/CD"],1,2),
 ("Elevance Health","QA Engineer — FHIR Interoperability","Remote","remote","contract","hcit",58,68,"hr",4,8,True,"employer",
  "HL7 FHIR R4 resource validation, SMART-on-FHIR auth flows. Sponsorship available for the right candidate.",
  "https://elevancehealth.com/careers",["HL7 FHIR R4","Postman","SMART-on-FHIR"],3,1),
 ("Cognizant","Lead QA Engineer — GenAI & Automation","Charlotte, NC","remote","fulltime","aiq",71000,112000,"yr",5,10,True,"employer",
  "Playwright plus GitHub Copilot-assisted test generation. We sponsor H1B transfers.",
  "https://careers.cognizant.com",["Playwright","GenAI","Copilot"],4,1),
 ("Walmart","SRE II — Supply Chain Platform","Bentonville, AR","hybrid","fulltime","sre",115000,140000,"yr",4,8,True,"employer",
  "Kubernetes, Prometheus, Terraform. Any visa considered.",
  "https://careers.walmart.com",["Kubernetes","Prometheus","Go","Terraform"],8,1),
]

COURSES = [
 ("Apache Kafka Series — Learn Kafka","Udemy","https://udemy.com",8499,"course",8,["Kafka"],
  "Producers, consumers, topics and partitions — fastest route to shipping Kafka tests."),
 ("AWS Certified Data Engineer — Associate","Amazon Web Services","https://aws.amazon.com/certification",15000,"cert",40,["Airflow","DBT","Kafka"],
  "Official AWS cert covering ingestion, transformation and orchestration."),
 ("dbt Fundamentals","dbt Labs","https://courses.getdbt.com",0,"course",5,["DBT"],
  "Free official course. dbt's built-in tests map almost one-to-one onto ETL QA."),
 ("Terraform Associate Certification","HashiCorp","https://hashicorp.com/certification",7050,"cert",25,["Terraform"],
  "Increasingly assumed for senior SDETs who own their test environments."),
 ("Google Cloud Professional Data Engineer","Google Cloud","https://cloud.google.com/certification",20000,"cert",50,["Airflow","Kafka"],
  "Recognised broadly, not just at GCP shops."),
 ("SpecFlow & ReqnRoll BDD for .NET","Pluralsight","https://pluralsight.com",2900,"course",6,["SpecFlow"],
  "Cucumber experience transfers almost completely — mostly syntax and tooling."),
]

CONNECTIONS = [
 ("Anil Kumar","Senior QA Engineer","Cognizant",1,"Worked together at TCS, 2021–2023"),
 ("Meera Sundaram","Engineering Manager","Cognizant",2,"Via Anil Kumar · both TCS alumni"),
 ("Deepa Nair","Data Engineer","UnitedHealth Group",1,"Webster University, same cohort"),
 ("James Okoro","Senior SDET","CVS Health",1,"Playwright community · conference 2025"),
 ("Sarah Lindqvist","QA Manager","Mastercard",1,"Current colleague"),
]


def run():
    print("Creating tables…")
    tables = init_db()
    db = SessionLocal()

    u = db.query(User).filter(User.email == "dev@careerpilot.local").first()
    if not u:
        u = User(email="dev@careerpilot.local", name="Santosh Reddy", slug="santoshreddy",
                 headline="Sr. SDET / QA Automation Engineer", location="St. Louis, MO",
                 work_auth=["h1b"], plan="pro", referral_code="santoshreddy")
        db.add(u); db.commit(); db.refresh(u)

    if not db.query(Position).filter(Position.user_id == u.id).count():
        for co, role, s_, f_, loc, bl in [
            ("Mastercard","Sr. SDET / Senior Quality Engineer",dt.date(2024,5,1),None,"O'Fallon, MO",
             ["Playwright (JS/TS) + Selenium Hybrid/POM framework for payment platforms",
              "ETL testing for payment pipelines; medallion-pattern lakehouse validation",
              "PEGA functional testing — case management and payment workflow automation",
              "GitHub Copilot–assisted test generation; Cypress browser automation",
              "PCI-DSS and OWASP security validation with Burp Suite"]),
            ("Tata Consultancy Services","QA Automation Engineer / API & Backend",dt.date(2019,9,1),dt.date(2023,12,31),"Hyderabad, India",
             ["HL7/FHIR validation and HIPAA compliance for healthcare payer systems",
              "PySpark ETL test frameworks across distributed big-data environments",
              "Data migration and reconciliation testing; Oracle and MySQL validation"]),
            ("CashAPona","QA Engineer",dt.date(2018,9,1),dt.date(2019,7,31),"Hyderabad, India",
             ["E-commerce checkout, payment gateway, and cross-browser automation"]),
        ]:
            db.add(Position(user_id=u.id, company=co, role=role, started_on=s_,
                            finished_on=f_, location=loc, bullets=bl))
        db.commit()

    if not db.query(UserSkill).filter(UserSkill.user_id == u.id).count():
        top = ["Playwright","Cypress","Selenium","API Testing","PySpark","AWS Redshift",
               "HL7/FHIR","PEGA","GitHub Copilot","ETL Testing"]
        rest = ["Java","Python","TypeScript","SQL","PL/SQL","C#","TestNG","JUnit","Cucumber",
                "Postman","RestAssured","JMeter","k6","Jenkins","GitHub Actions","Azure DevOps",
                "Docker","Kubernetes","Burp Suite","Tricentis Tosca","Appium"]
        for s_ in top:  db.add(UserSkill(user_id=u.id, skill=s_, is_top=True))
        for s_ in rest: db.add(UserSkill(user_id=u.id, skill=s_, is_top=False))
        db.commit()

    now = dt.datetime.now(dt.timezone.utc)
    for (co,title,loc,mode,emp,fam,cmin,cmax,unit,emin,emax,f500,ctype,desc,url,skills,days,seen) in JOBS:
        fp = fingerprint(co, title, loc)
        if db.query(Job).get(fp): continue
        v = parse_visa(desc)          # ← the parser, running for real
        db.add(Job(fingerprint=fp, source="seed", company=co, company_type=ctype,
                   is_fortune500=f500, title=title, location=loc, work_mode=mode,
                   employment=emp, description=desc, apply_url=url,
                   comp_min=cmin, comp_max=cmax, comp_unit=unit,
                   exp_min=emin, exp_max=emax,
                   visa_usc=v["usc"], visa_gc=v["gc"], visa_h1b=v["h1b"], visa_opt=v["opt"],
                   role_family=fam, career_field=TAXONOMY_SAMPLE.get(fam,"Quality"),
                   required_skills=skills,
                   posted_at=now - dt.timedelta(days=days),
                   first_seen=now - dt.timedelta(days=days), last_seen=now,
                   seen_count=seen, relisted=seen >= 3, active=True))
    db.commit()

    if not db.query(Course).count():
        for n,p_,url,price,kind,hrs,sk,d in COURSES:
            db.add(Course(name=n, provider=p_, url=url, price_cents=price,
                          kind=kind, hours=hrs, skills=sk, description=d))
        db.commit()

    if not db.query(Connection).filter(Connection.user_id == u.id).count():
        for n,r,co,deg,how in CONNECTIONS:
            db.add(Connection(user_id=u.id, name=n, role=r, company=co, degree=deg, how_known=how))
        db.commit()

    if not db.query(Referral).filter(Referral.referrer_id == u.id).count():
        for email, status in [("anil@example.com","active"),("deepa@example.com","active"),
                              ("james@example.com","joined"),("priyanka@example.com","invited")]:
            db.add(Referral(referrer_id=u.id, email_invited=email, status=status))
        db.commit()

    ps = db.query(Position).filter(Position.user_id == u.id).all()
    total = sum(p.months for p in ps)
    print(f"\n  {len(tables)} tables")
    print(f"  user: {u.name} <{u.email}> plan={u.plan}")
    print(f"  {len(ps)} positions = {total} months ({total//12}y {total%12}m)")
    for p in ps: print(f"     {p.company:28} {p.duration_label}")
    print(f"  {db.query(Job).count()} jobs, {db.query(Course).count()} courses, "
          f"{db.query(Connection).count()} connections, {db.query(Referral).count()} referrals")
    print("\n  visa flags parsed from JD text:")
    for j in db.query(Job).all():
        print(f"     {j.company:22} usc={j.visa_usc} gc={j.visa_gc} h1b={j.visa_h1b} opt={j.visa_opt}")
    db.close()
    print("\nReady →  uvicorn api.main:app --reload")


if __name__ == "__main__":
    run()
