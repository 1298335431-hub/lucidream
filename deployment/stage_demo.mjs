// Build a NEW allowlisted release folder; never package the working directory.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const archive = process.argv[2];
const expected = process.argv[3];
const headlessWheel = process.argv[4];
const headlessHash = process.argv[5];
if (!archive || !/^[a-f0-9]{64}$/.test(expected || '')) throw new Error('Verified Node archive + SHA256 required');
const bytes = fs.readFileSync(archive);
if (crypto.createHash('sha256').update(bytes).digest('hex') !== expected) throw new Error('Node checksum mismatch');
if (!headlessWheel || !/^[a-f0-9]{64}$/.test(headlessHash || '') || crypto.createHash('sha256').update(fs.readFileSync(headlessWheel)).digest('hex') !== headlessHash) throw new Error('Verified headless OpenCV wheel required');
if (!fs.readFileSync(path.join(root, 'dist/index.html'), 'utf8').includes('type="module"')) throw new Error('Build frontend first');
const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'lucidream-release-'));
function copy(source, target = source) {
  const to = path.join(stage, target);
  fs.mkdirSync(path.dirname(to), {recursive:true});
  fs.cpSync(path.join(root, source), to, {recursive:true, filter: p => !['__pycache__', '.DS_Store'].includes(path.basename(p)) && !p.endsWith('.pyc')});
}
copy('backend/app');
copy('dist');
copy('data/knowledge/dream_sources.sqlite3');
copy('data/knowledge/自建知识库/processed/cards.jsonl', 'data/knowledge/cards.jsonl');
copy('integrations/zhihu-login/server.mjs');
copy('integrations/zhihu-login/hackathon.config.json');
copy('integrations/zhihu-login/lib');
copy('deployment/demo_boot.py', 'main.py');
copy('deployment/demo_server.py', 'demo_server.py');
fs.writeFileSync(path.join(stage, 'requirements.txt'), fs.readFileSync(path.join(root,'backend/requirements.txt'),'utf8').split('\n').filter(line => !line.startsWith('pytest')).join('\n'));
fs.mkdirSync(path.join(stage,'runtime'));
fs.copyFileSync(archive, path.join(stage,'runtime/node.tar.gz'));
// Keep the server-only cv2 isolated; RapidOCR's desktop dependency must not shadow it.
execFileSync('unzip', ['-q', headlessWheel, '-d', path.join(stage, 'vendor')]);
fs.writeFileSync(path.join(stage,'.vefaasignore'), '.vefaas/\n.env\n.env.*\n**/__pycache__/\n');
// Reject secrets/data by names even when an allowlisted directory changes later.
const files = fs.readdirSync(stage,{recursive:true,withFileTypes:true}).filter(x=>x.isFile()).map(x=>path.relative(stage,path.join(x.parentPath,x.name)));
for (const file of files) {
  if (/(^|\/)\.env|dreamcard\.db|\.log$|\.pem$|\.key$/.test(file)) throw new Error('Forbidden release file');
}
console.log(JSON.stringify({stage,files:files.length,nodeSha256:expected,privateDataIncluded:false}));
