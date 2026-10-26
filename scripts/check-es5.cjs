const fs = require('fs');
const acorn = require('acorn');
const html = fs.readFileSync('dashboard.html', 'utf8');
const script = html.split('<script>')[1].split('</script>')[0];
acorn.parse(script, {ecmaVersion: 5});
console.log('Dashboard JavaScript parses as ECMAScript 5.');
