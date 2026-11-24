#!/bin/bash
# Autorise l'accès au serveur de l'hôtel en HTTP (réseau local) et l'appareil photo. À lancer sur Mac.
set -e
PLIST="$(dirname "$0")/../ios/App/App/Info.plist"
PB=/usr/libexec/PlistBuddy
$PB -c "Delete :NSAppTransportSecurity" "$PLIST" 2>/dev/null || true
$PB -c "Add :NSAppTransportSecurity dict" "$PLIST"
$PB -c "Add :NSAppTransportSecurity:NSAllowsLocalNetworking bool true" "$PLIST"
$PB -c "Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true" "$PLIST"
$PB -c "Delete :NSCameraUsageDescription" "$PLIST" 2>/dev/null || true
$PB -c "Add :NSCameraUsageDescription string 'L appareil photo sert à scanner le QR code des cartes de membre.'" "$PLIST"
$PB -c "Delete :NSLocalNetworkUsageDescription" "$PLIST" 2>/dev/null || true
$PB -c "Add :NSLocalNetworkUsageDescription string 'Connexion au logiciel de la réception sur le réseau de l hôtel.'" "$PLIST"
echo "Info.plist adapté (réseau local + appareil photo)."
