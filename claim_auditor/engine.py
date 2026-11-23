from __future__ import annotations
from collections import Counter
from .schemas import Run, Manifest, Claim

class EvidenceError(ValueError):
    pass

def evaluate(runs: list[Run], manifest: Manifest, claim: Claim) -> dict:
    if claim.protocol_id != manifest.protocol_id or claim.target_class != manifest.target_class:
        raise EvidenceError('Claim does not match manifest protocol/target class')
    if claim.dataset_id not in manifest.expected_splits:
        raise EvidenceError('Dataset missing in manifest')
    expected = manifest.expected_splits[claim.dataset_id]
    if claim.expected_split_ids != expected:
        raise EvidenceError('Claim split identities or order differ from manifest')
    if claim.baseline_method == claim.challenger_method:
        raise EvidenceError('Baseline and challenger must differ')
    if claim.baseline_method not in manifest.expected_methods or claim.challenger_method not in manifest.expected_methods:
        raise EvidenceError('Method not declared in manifest')
    if claim.fpr_limit not in manifest.fpr_limits:
        raise EvidenceError('FPR limit not declared in manifest')
    # Validate the entire import, not merely rows selected by the claim.
    counts=Counter((r.dataset_id,r.protocol_id,r.split_id,r.method_id,r.target_class,r.fpr_limit) for r in runs)
    expected_keys={(ds,manifest.protocol_id,s,m,manifest.target_class,f) for ds,ss in manifest.expected_splits.items() for s in ss for m in manifest.expected_methods for f in manifest.fpr_limits}
    if set(counts) != expected_keys or any(v!=1 for v in counts.values()):
        missing=len(expected_keys-set(counts));extra=len(set(counts)-expected_keys);duplicates=sum(n-1 for n in counts.values())
        raise EvidenceError(f'Incomplete or duplicated evidence (missing={missing}, unexpected={extra}, duplicates={duplicates})')
    idx={(r.dataset_id,r.protocol_id,r.split_id,r.method_id,r.target_class,r.fpr_limit):r for r in runs}
    out=[];wins=losses=ties=joint=0;eligible_b=eligible_c=0
    for split in expected:
        def get(method):return idx[(claim.dataset_id,claim.protocol_id,split,method,claim.target_class,claim.fpr_limit)]
        base,chall=get(claim.baseline_method),get(claim.challenger_method)
        b_ok=base.test_fpr<=claim.fpr_limit+1e-12
        c_ok=chall.test_fpr<=claim.fpr_limit+1e-12
        eligible_b+=b_ok;eligible_c+=c_ok
        together=b_ok and c_ok
        delta=chall.test_recall-base.test_recall
        outcome='NOT_JOINTLY_ELIGIBLE'
        if together:
            joint+=1
            if delta>claim.recall_margin+1e-12:outcome='WIN';wins+=1
            elif delta< -claim.recall_margin-1e-12:outcome='LOSS';losses+=1
            else:outcome='TIE';ties+=1
        out.append(dict(split_id=split,baseline_fpr=base.test_fpr,challenger_fpr=chall.test_fpr,
                        baseline_recall=base.test_recall,challenger_recall=chall.test_recall,
                        baseline_feasible=b_ok,challenger_feasible=c_ok,jointly_feasible=together,
                        recall_delta=round(delta,12),outcome=outcome))
    if not joint:finding='NO_JOINT_ELIGIBLE'
    elif wins and losses:finding='MIXED'
    elif wins and not losses:finding='POSITIVE_ALL_ELIGIBLE' if ties==0 else 'POSITIVE_OR_TIED'
    elif losses and not wins:finding='NEGATIVE_ALL_ELIGIBLE' if ties==0 else 'NEGATIVE_OR_TIED'
    else:finding='TIED_ONLY'
    strict=joint==len(expected) and wins==len(expected)
    conditional=joint>0 and losses==0 and wins>0
    supported=(strict if claim.claim_type=='universal_operational_advantage' else conditional)
    return dict(claim=claim.model_dump(),integrity='PASS',operational={'expected_splits':len(expected),
       'baseline_feasible':eligible_b,'challenger_feasible':eligible_c,'jointly_feasible':joint,
       'all_splits_jointly_feasible':joint==len(expected)},comparison={'wins':wins,'losses':losses,'ties':ties,
       'finding':finding}, claim_support='OBSERVED_CONDITIONAL_SUPPORT' if supported else 'NOT_SUPPORTED_AS_STATED',
       statistical_superiority='NOT_ESTABLISHED',evidence=out,
       limitations=['Descriptive comparison only; no population-level inference.',
       'IP-pair groups do not establish independent collection sessions.',
       'Test FPR is evaluated after threshold selection, not guaranteed by the target.'])
