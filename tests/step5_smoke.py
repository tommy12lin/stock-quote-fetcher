"""Manual container smoke entrypoint; outputs contain no environment secrets."""
from pathlib import Path
import os
import sys
import tomllib
from stock_quote_fetcher.cli import main

# Refresh Docker --env-file semantics for credentials the user added after startup.
for line in Path('/workspace/.env').read_text().splitlines():
    if line and not line.lstrip().startswith('#') and '=' in line:
        key,value = line.split('=',1)
        if key in {'DB_PASSWORD','FINNHUB_API_KEY'}:
            os.environ[key] = value
print('Finnhub key present:',bool(os.environ.get('FINNHUB_API_KEY','').strip()))
text = Path('/workspace/config.toml').read_text()
doc = tomllib.loads(text)
# Use the current project's database settings, explicit comparison sources and CA.
lines = ['[database]']
for key,value in doc.get('database',{}).items():
    if key == 'password':
        raise ValueError('secret in public config')
    lines.append(f'{key} = {value!r}' if isinstance(value,str) else f'{key} = {value}')
lines += ['[providers]','valuation = "yahoo"','comparison = ["finnhub", "twse", "tpex"]',
          '[tls]','company_ca_file = "/workspace/secrets/company-root-ca.crt"',
          'relaxed_providers = ["finnhub", "twse", "tpex"]',
          'relaxed_sources = ["twse_companies", "twse_funds", "tpex_isin"]']
Path('/tmp/step5.toml').write_text('\n'.join(lines)+'\n')
sys.exit(main(['quote','--input','/workspace/examples/holdings.csv','--config','/tmp/step5.toml','--output','/tmp/step5-output']))
