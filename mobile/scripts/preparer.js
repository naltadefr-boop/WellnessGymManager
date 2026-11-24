// Copie l'application mobile (la même que celle servie sous /m/) dans www/.
// Une seule base de code : toute amélioration de gym/static/gym/mobile profite aux deux versions.
const fs = require("fs"), path = require("path");
const src = path.resolve(__dirname, "../../gym/static/gym/mobile");
const dst = path.resolve(__dirname, "../www");
fs.rmSync(dst, { recursive: true, force: true });
fs.mkdirSync(dst, { recursive: true });
for (const f of fs.readdirSync(src)) {
  if (f === "sw.js") continue; // inutile dans l'application native
  fs.copyFileSync(path.join(src, f), path.join(dst, f));
}
console.log("Application copiée dans", dst);
