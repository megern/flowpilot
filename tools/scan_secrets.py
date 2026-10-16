"""Conservative offline secret-pattern scan; complement with hosted secret scanning."""
from pathlib import Path
import re
patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}", r"gh[pousr]_[A-Za-z0-9]{30,}"]
findings = []
for root in ("app", "tests", "examples"):
    for path in Path(root).rglob("*"):
        if path.is_file() and path.suffix in {".py", ".json", ".txt"}:
            content = path.read_text()
            if any(re.search(pattern, content) for pattern in patterns):
                findings.append(str(path))
if findings:
    raise SystemExit("Potential secrets: " + ", ".join(findings))
print("No configured secret patterns detected in app/tests/examples")
