"""Rebuild fingerprinted browser assets after editing source JS/CSS."""
from pathlib import Path
import hashlib,re
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
SCRIPTS=['project_sharing.js', 'workspace_switch.js', 'mobile.js', 'file_drop.js', 'builders.js', 'app.js', 'workspace.js', 'productivity.js', 'estimate_workspace.js', 'navigation.js', 'help_chat.js', 'estimate_extras.js', 'light_prices.js', 'v23.js', 'profile.js', 'quotation_import.js', 'import_history.js', 'project_transfer.js', 'performance.js']
def emit(prefix,extension,body):
    digest=hashlib.sha256(body.encode()).hexdigest()[:12]
    name=f'{prefix}.{digest}.{extension}'
    for old in ASSETS.glob(f'{prefix}.*.{extension}'):
        if re.fullmatch(rf'{prefix}\.[a-f0-9]{{12}}\.{extension}',old.name):old.unlink()
    (ASSETS/name).write_text(body)
    return name
for obsolete in ['workspace.css','theme.css','responsive.css','v23.css','v231.css','v232.css','v233.css','v235.css','v236.css','v24.css']:
    (ASSETS/obsolete).unlink(missing_ok=True)
theme=emit('theme','js',(ASSETS/'theme.js').read_text())
css=emit('styles','css',(ASSETS/'styles.css').read_text())
js=emit('app','js','\n;\n'.join('/* '+f+' */\n'+(ASSETS/f).read_text() for f in SCRIPTS))
p=ASSETS/'index.html';html=p.read_text()
html=re.sub(r'/assets/theme(?:\.[a-f0-9]{12})?\.js(?:\?[^" ]+)?','/assets/'+theme,html)
html=re.sub(r'/assets/styles(?:\.[a-f0-9]{12})?\.css(?:\?[^" ]+)?','/assets/'+css,html)
html=re.sub(r'/assets/(?:app\.bundle|app\.[a-f0-9]{12})\.js(?:\?[^" ]+)?','/assets/'+js,html)
p.write_text(html)
print('Built',css,js)
