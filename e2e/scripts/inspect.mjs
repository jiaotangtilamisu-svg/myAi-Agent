import { command } from '../lib/session.mjs';
const role = process.argv[2] || 'shop';
console.log(JSON.stringify(await command({ op: 'inspect', role }), null, 2));
