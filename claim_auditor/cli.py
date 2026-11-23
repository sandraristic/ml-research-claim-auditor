import argparse, csv, json
from pathlib import Path
from .adapters.mitm import import_zip
from .schemas import Run

FIELDS=list(Run.model_fields)

def main(argv=None):
    ap=argparse.ArgumentParser(description='MVP M1 - normalize MITM experimental metrics')
    ap.add_argument('--corrected',required=True)
    ap.add_argument('--stability',required=True)
    ap.add_argument('--out',default='claim_auditor_import')
    args=ap.parse_args(argv)
    # Import all and validate first; do not output partial results.
    imports=[(name,import_zip(getattr(args,name),name)) for name in ('corrected','stability')]
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    summary=[]
    for name,(runs,manifest,warnings,sha) in imports:
        folder=out/name;folder.mkdir(exist_ok=True)
        with (folder/'runs.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
            writer.writerows([r.model_dump() for r in runs])
        (folder/'manifest.json').write_text(manifest.model_dump_json(indent=2),encoding='utf-8')
        report={'source_sha256':sha,'rows':len(runs),'warnings':warnings,'status':'PASS_WITH_WARNINGS' if warnings else 'PASS'}
        (folder/'import_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        summary.append((name,len(runs),report['status']))
    for name,count,status in summary:print(f'{name}: {count} rows; {status}')
    print('Output:',out.resolve())

if __name__=='__main__':main()
