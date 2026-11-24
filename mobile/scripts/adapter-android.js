// Autorise la connexion HTTP au serveur de l'hôtel (réseau local) et l'appareil photo.
const fs = require("fs"), path = require("path");
const f = path.resolve(__dirname, "../android/app/src/main/AndroidManifest.xml");
if (!fs.existsSync(f)) { console.error("Projet Android absent : lancez d'abord npm run android:init"); process.exit(1); }
let x = fs.readFileSync(f, "utf8");
if (!x.includes("usesCleartextTraffic")) x = x.replace("<application", '<application android:usesCleartextTraffic="true"');
for (const p of ["android.permission.CAMERA", "android.permission.INTERNET", "android.permission.VIBRATE"]) {
  if (!x.includes(p)) x = x.replace("<application", `<uses-permission android:name="${p}" />\n    <application`);
}
if (!x.includes("android.hardware.camera")) x = x.replace("<application", '<uses-feature android:name="android.hardware.camera" android:required="false" />\n    <application');
fs.writeFileSync(f, x);
console.log("AndroidManifest.xml adapté (réseau local HTTP + appareil photo).");
