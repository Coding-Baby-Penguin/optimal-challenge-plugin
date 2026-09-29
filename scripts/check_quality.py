#!/usr/bin/env python3
"""One truthful structural gate, with a separately verified host release gate."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIRECT_VERSIONS={"jsonschema":"4.25.1","PyYAML":"6.0.2"}

def validate_environment(python_version,installed_versions):
    errors=[]
    if tuple(python_version[:2])!=(3,12): errors.append("Use CPython 3.12; bootstrap a clean environment with requirements-dev.lock")
    for name,version in DIRECT_VERSIONS.items():
        if installed_versions.get(name)!=version: errors.append(f"Install {name}=={version} with --require-hashes -r requirements-dev.lock")
    return errors

def execute_check(name,command,root,*,timeout_seconds=600):
    started=time.monotonic()
    try:
        result=subprocess.run(command,cwd=root,check=False,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout_seconds)
        output=result.stdout+result.stderr
        status="pass" if result.returncode==0 else "failed"
        if name=="unit":
            counts=[int(value) for value in re.findall(r"\bRan\s+(\d+)\s+tests?\b",output)]
            if not counts or max(counts)==0:
                status="failed"
                output+="\nUnit discovery found zero tests or no verifiable count; refusing a green status.\n"
        return {"name":name,"status":status,"returncode":result.returncode,"seconds":round(time.monotonic()-started,3),"observed_tests":max(counts) if name=="unit" and counts else None,"output":output}
    except subprocess.TimeoutExpired as exc:
        def decoded(part):
            if isinstance(part,bytes): return part.decode("utf-8",errors="replace")
            return part if isinstance(part,str) else ""
        output=decoded(exc.stdout)+decoded(exc.stderr)
        return {"name":name,"status":"blocked","returncode":None,"seconds":round(time.monotonic()-started,3),"output":output+f"\n{name} timeout after {timeout_seconds} seconds; partial output retained.\n"}
    except OSError as exc:
        return {"name":name,"status":"blocked","returncode":None,"seconds":round(time.monotonic()-started,3),"output":f"{name} could not start: {type(exc).__name__}: {exc}"}


def release_gate(evidence_root):
    if evidence_root is None: return {"status":"blocked","reasons":["Authentic current host evidence is required; structural success cannot establish release acceptance"]}
    try:
        if __package__: from .evaluation_evidence import verify_release_evidence
        else: from evaluation_evidence import verify_release_evidence
    except ImportError:
        return {"status":"blocked","reasons":["Trusted release evidence verifier is not yet available; supplied status JSON is not proof"]}
    try:
        result=verify_release_evidence(Path(evidence_root))
    except (OSError,ValueError,TypeError) as exc:
        return {"status":"blocked","reasons":[f"Evidence verification failed: {type(exc).__name__}"]}
    if not isinstance(result,dict) or result.get("status")!="verified":
        return {"status":"blocked","reasons":result.get("reasons",["Required current evidence is unverified"]) if isinstance(result,dict) else ["Invalid verifier result"]}
    return result

def repository_checks(root):
    """Inspect tracked text only; secret matches report paths, never contents."""
    result=subprocess.run(["git","ls-files","-z"],cwd=root,capture_output=True,check=True)
    tracked={name for name in result.stdout.decode("utf-8").split("\0") if name}
    errors=[]
    secret=re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{24,}\b|\bghp_[A-Za-z0-9]{30,}\b")
    links=re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for relative in sorted(tracked):
        path=root / relative
        if path.is_symlink(): errors.append(f"Tracked symlink: {relative}");continue
        if not path.is_file(): errors.append(f"Missing tracked file: {relative}");continue
        raw=path.read_bytes()
        if b"\0" in raw: continue
        try: text=raw.decode("utf-8")
        except UnicodeDecodeError: continue
        if b"\r\n" in raw: errors.append(f"Noncanonical LF text: {relative}")
        if secret.search(text): errors.append(f"Potential secret in tracked text: {relative}")
        if path.suffix.lower()==".md":
            for match in links.finditer(text):
                target=match.group(1).strip().split(' "',1)[0].strip("<>")
                if not target or target.startswith(("#","/")) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:",target): continue
                target=target.split("#",1)[0]
                resolved=(path.parent / target).resolve()
                if not resolved.exists(): errors.append(f"Broken relative Markdown link: {relative} -> {target}")
    return errors

def run_quality(mode,output,evidence_root=None):
    installed={}
    for name in DIRECT_VERSIONS:
        try: installed[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: installed[name]=None
    prerequisite_errors=validate_environment(sys.version_info,installed)
    host=release_gate(evidence_root) if mode=="release" else {"status":"unverified","reasons":["Structural checks do not run host acceptance"]}
    summary={"schema_version":1,"mode":mode,"python":sys.version.split()[0],"dependencies":installed,"structural":{"status":"blocked" if prerequisite_errors else "pending","reasons":prerequisite_errors},"host":host,"checks":[]}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if not prerequisite_errors:
        checks=[("unit",[sys.executable,"-m","unittest","discover","-v"]),("integrated",[sys.executable,"scripts/validate.py"]),("adversarial",[sys.executable,"scripts/adversarial_review.py"]),("package",[sys.executable,"scripts/package_release.py"])]
        for name,command in checks:
            result=execute_check(name,command,ROOT)
            log=output.parent / f"check-{name}.log"
            output_text=result.pop("output")
            output_text=re.sub(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "[REDACTED PRIVATE KEY]",output_text)
            output_text=re.sub(r"\b(?:sk-[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{30,})\b","[REDACTED TOKEN]",output_text)
            log.write_text(output_text,encoding="utf-8",newline="\n")
            result["log"]=str(log)
            summary["checks"].append(result)
        errors=repository_checks(ROOT)
        summary["checks"].append({"name":"links-lf-secrets","status":"failed" if errors else "pass","reasons":errors})
        summary["structural"]["status"]="pass" if all(check["status"]=="pass" for check in summary["checks"]) else "failed"
    structural_ok=summary["structural"]["status"]=="pass"
    summary["status"]="pass" if structural_ok and (mode=="structural" or host["status"]=="verified") else "blocked" if prerequisite_errors or (structural_ok and mode=="release") else "failed"
    output.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8",newline="\n")
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("structural","release"),default="structural")
    parser.add_argument("--output",type=Path,default=Path("tmp/quality/summary.json"))
    parser.add_argument("--evidence-root",type=Path)
    args=parser.parse_args()
    summary=run_quality(args.mode,args.output,args.evidence_root)
    print(json.dumps({"status":summary["status"],"structural":summary["structural"],"host":summary["host"],"summary":str(args.output)},indent=2))
    return 0 if summary["status"]=="pass" else 2 if summary["status"]=="blocked" else 1

if __name__=="__main__": raise SystemExit(main())
