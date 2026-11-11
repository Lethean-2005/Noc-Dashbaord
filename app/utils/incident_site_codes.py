"""Display all incident site identities without guessing unknown prefixes."""
import re


def incident_site_codes(row, known_codes):
    known = {str(code).strip().upper() for code in known_codes if code}
    result = []
    for field in ("site_text", "site_code"):
        for token in re.split(r"[,;/|\s]+", str(row.get(field) or "")):
            code = token.strip().upper()
            if not code:
                continue
            # Registered alphanumeric codes win over a possible province prefix.
            if code not in known and re.fullmatch(r"[A-Z]{2}\d+", code) and code[2:] in known:
                code = code[2:]
            if code not in result:
                result.append(code)
    return "/".join(result)
