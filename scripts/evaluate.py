"""Record observed permission-matrix outcomes from the existing integration tests."""
import argparse
import json
from pathlib import Path
import platform
import sys

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Re-run the API permission matrix on the disposable synthetic seed')
    parser.add_argument('--disposable-lab',action='store_true');args=parser.parse_args()
    if not args.disposable_lab:parser.error('explicit --disposable-lab confirmation is required')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import os
    import unittest
    import django
    from tests.test_api import ApiTests
    from django.db import connection
    instances=[ApiTests(name) for name in ('test_read_permission_matrix_covers_all_roles_and_tenants','test_write_permission_matrix_covers_editors_viewers_and_nonmembers')]
    for instance in instances:instance.matrix_records=[]
    result=unittest.TextTestRunner(stream=sys.stderr,verbosity=1).run(unittest.TestSuite(instances))
    cases=[case for instance in instances for case in instance.matrix_records]
    with connection.cursor() as cursor:
        cursor.execute('SHOW server_version');postgres=cursor.fetchone()[0]
    connection.close()
    summary={'cases':len(cases),'expected_allowed':sum(c['expected']<400 for c in cases),'expected_denied':sum(c['expected']==403 for c in cases),
        'unexpected_denials':sum(c['expected']<400 and c['actual']>=400 for c in cases),
        'unexpected_acceptances':sum(c['expected']==403 and c['actual']<400 for c in cases),
        'status_mismatches':sum(c['expected']!=c['actual'] for c in cases)}
    complete=result.wasSuccessful() and len(cases)==42
    print(json.dumps({'schema_version':1,'source':'synthetic_seed','method':'Existing Django Client tests with enforced CSRF and real PostgreSQL; force_login for matrix identities, not password-authentication evaluation.',
        'environment':{'python':platform.python_version(),'django':django.get_version(),'postgresql':postgres,'code_revision':os.environ.get('GITHUB_SHA','local_unrecorded'),'run_url':f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}" if os.environ.get('GITHUB_RUN_ID') else None},
        'completed':complete,'summary':summary,'cases':cases,'limitations':['Bounded lab role/tenant matrix; no claim of exhaustive security coverage or real-world detection accuracy.',
            'Real login/session behavior is tested separately by the suite, HTTP demo and Chromium.']},separators=(',',':')))
    sys.exit(0 if complete else 1)
