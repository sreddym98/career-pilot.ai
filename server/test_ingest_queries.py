import importlib.util
import os

root = os.path.dirname(os.path.abspath(__file__))
module_path = os.path.join(root, 'ingest', 'run.py')
spec = importlib.util.spec_from_file_location('careerpilot_ingest_run', module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

required = [
    'monster qa jobs usa',
    'linkedin sdet jobs usa',
    'linkedin software engineer jobs usa',
    'linkedin data analyst jobs usa',
    'linkedin product manager jobs usa',
    'linkedin qa jobs usa',
    'ziprecruiter automation jobs usa',
    'techfetch quality jobs usa',
    'benchinfo sdet jobs usa',
    'software engineer jobs usa',
    'quality engineer jobs usa',
    'qa jobs usa',
    'product manager jobs usa',
    'data analyst jobs usa',
    'business analyst jobs usa',
    'contract jobs usa',
]
missing = [q for q in required if q not in [s.lower() for s in mod.AGG_QUERIES]]
assert not missing, f'Missing required query strings: {missing}'
assert hasattr(mod, 'ALL_ROLE_AGG_QUERIES')
assert hasattr(mod, 'TECH_AGG_QUERIES')
assert hasattr(mod, 'QA_AGG_QUERIES')
assert hasattr(mod, 'CONTRACT_AGG_QUERIES')

# Staffing-vs-employer classifier should become conservative and explicit.
assert mod.company_type('Net2Source Inc', 'We are hiring for our client and need a QA engineer') == 'staffing'
assert mod.company_type('Affirm', 'Affirm is hiring for a full-time QA engineer role') == 'employer'
assert mod.company_type('Garner Health', 'Our client is seeking a product manager') == 'staffing'
assert mod.company_type('Ro', 'Ro is hiring a senior software engineer') == 'employer'
assert mod.guess_company_type('Compunnel', 'QA Automation Engineer') == 'staffing'
assert mod.guess_company_type('Google', 'Senior software engineer full-time') == 'employer'
print('ingest query coverage ok')
