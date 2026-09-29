"""Frozen holistic rubric; awards belong to independently verified review records."""
from collections.abc import Mapping

CONTRACT = {
    "purpose": (6,8.0), "user_control": (6,7.5), "host_behavior": (12,3.0),
    "correctness": (12,6.5), "architecture": (6,6.5), "security": (7,7.5),
    "test_quality": (7,7.5), "efficiency": (4,5.0), "recovery": (3,5.5),
    "platform": (3,4.5), "installation": (3,6.0), "packaging": (5,6.5),
    "documentation": (6,6.5), "cleanliness": (20,6.5),
}

def validate_rubric(data):
    if not isinstance(data,Mapping): return ["rubric must be an object"]
    errors=[]
    dimensions=data.get("dimensions")
    if not isinstance(dimensions,list): return ["dimensions must be an array"]
    if len(dimensions)!=14: errors.append("all fourteen frozen dimensions are required")
    seen=[]
    for item in dimensions:
        if not isinstance(item,Mapping) or not isinstance(item.get("id"),str) or item["id"] not in CONTRACT:
            errors.append("unknown dimension");continue
        name=item["id"];seen.append(name)
        weight,baseline=CONTRACT[name]
        if item.get("weight")!=weight or item.get("baseline")!=baseline: errors.append(name+": frozen weight or baseline changed")
        if item.get("target")!=(10 if name=="cleanliness" else 9.5): errors.append(name+": target changed")
        if item.get("awarded_score") is not None: errors.append(name+": an unverified target cannot award points")
        if not isinstance(item.get("required_evidence"),list) or not item["required_evidence"]: errors.append(name+": evidence checklist missing")
    if set(seen)!=set(CONTRACT) or len(seen)!=len(set(seen)): errors.append("dimension IDs must exactly match the frozen contract")
    if data.get("claim_status")!="unawarded": errors.append("rubric targets must remain unawarded; use independent review evidence")
    return errors
