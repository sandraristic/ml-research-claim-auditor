import argparse,csv,json
from pathlib import Path
from .schemas import Run,Manifest,Claim
from .engine import evaluate, EvidenceError

def main(argv=None):
    ap=argparse.ArgumentParser(description='M2 descriptive claim evaluator')
    ap.add_argument('--input',required=True,help='M1 normalized folder with runs.csv and manifest.json')
    ap.add_argument('--claim',required=True,help='Claim JSON')
    ap.add_argument('--out',required=True)
    args=ap.parse_args(argv)
    folder=Path(args.input)
    manifest=Manifest.model_validate_json((folder/'manifest.json').read_text(encoding='utf-8'))
    claim=Claim.model_validate_json(Path(args.claim).read_text(encoding='utf-8'))
    with (folder/'runs.csv').open(newline='',encoding='utf-8') as f:
        runs=[Run.model_validate({k:(None if v=='' else v) for k,v in row.items()}) for row in csv.DictReader(f)]
    result=evaluate(runs,manifest,claim)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/'audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    with (out/'split_evidence.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(result['evidence'][0]));writer.writeheader();writer.writerows(result['evidence'])
    summary=['# Claim audit (descriptive only)','',f"Claim: {claim.challenger_method} vs {claim.baseline_method}; {claim.dataset_id} / {claim.protocol_id}",
      f"Maximum test FPR: {claim.fpr_limit:.2%}; target class: {claim.target_class}",
      f"Expected splits: {result['operational']['expected_splits']}; both feasible: {result['operational']['jointly_feasible']}",
      f"Wins / losses / ties: {result['comparison']['wins']} / {result['comparison']['losses']} / {result['comparison']['ties']}",
      f"Conditional finding: {result['comparison']['finding']}",f"Claim support: {result['claim_support']}",
      'Statistical superiority: NOT_ESTABLISHED','', '## Limitations',*[f'- {s}' for s in result['limitations']]]
    (out/'audit.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    print('Integrity: PASS')
    print('Jointly FPR feasible:',result['operational']['jointly_feasible'],'/',result['operational']['expected_splits'])
    print('Wins/Losses/Ties:',result['comparison']['wins'],result['comparison']['losses'],result['comparison']['ties'])
    print('Finding:',result['comparison']['finding'])
    print('Claim support:',result['claim_support'])
    print('Statistical superiority: NOT_ESTABLISHED')
    print('Saved:',out.resolve())

if __name__=='__main__':main()
