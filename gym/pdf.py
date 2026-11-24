"""
Génération des documents PDF : facture, reçu simplifié, carte de membre, rapports.
Bibliothèque : ReportLab (fiable, sans dépendance système, fonctionne sous Windows).
"""
from io import BytesIO

import qrcode
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Flowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .models import Formule, Parametres, Transaction
from .services import duree_lisible, fcfa

VERT = colors.HexColor("#0F3D36")
VERT_CLAIR = colors.HexColor("#E8F1EE")
OR = colors.HexColor("#B8913A")
GRIS = colors.HexColor("#5B6B67")
LIGNE = colors.HexColor("#D5DEDB")
ROUGE = colors.HexColor("#B42318")


def _st(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#1D2A27"))
    base.update(kw)
    return ParagraphStyle(name, **base)


S_NORMAL = _st("n")
S_PETIT = _st("p", fontSize=8, leading=10, textColor=GRIS)
S_GRAS = _st("g", fontName="Helvetica-Bold")
S_TITRE_ETAB = _st("te", fontName="Helvetica-Bold", fontSize=18, leading=21, textColor=VERT)
S_SOUS_TITRE = _st("st", fontSize=9.5, textColor=OR, fontName="Helvetica-Bold")
S_DOC = _st("doc", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=VERT, alignment=TA_RIGHT)
S_DROITE = _st("dr", alignment=TA_RIGHT)
S_CENTRE = _st("ce", alignment=TA_CENTER)
S_SECTION = _st("se", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)


def _dt(d):
    return timezone.localtime(d).strftime("%d/%m/%Y à %H:%M") if d else "—"


def _logo_flowable(params, taille=22 * mm):
    if params.logo:
        try:
            img = ImageReader(params.logo.path)
            w, h = img.getSize()
            ratio = min(taille / w, taille / h)
            return Image(params.logo.path, width=w * ratio, height=h * ratio)
        except Exception:
            pass
    return _Embleme(taille)


class _Embleme(Flowable):
    """Emblème par défaut (monogramme W) tant qu'aucun logo n'est chargé."""

    def __init__(self, taille):
        super().__init__()
        self.taille = taille

    def wrap(self, *a):
        return self.taille, self.taille

    def draw(self):
        c, t = self.canv, self.taille
        c.setFillColor(VERT)
        c.circle(t / 2, t / 2, t / 2, stroke=0, fill=1)
        c.setStrokeColor(OR)
        c.setLineWidth(1.2)
        c.circle(t / 2, t / 2, t / 2 - 2.2, stroke=1, fill=0)
        c.setFillColor(OR)
        c.setFont("Helvetica-Bold", t * 0.48)
        c.drawCentredString(t / 2, t * 0.31, "W")


def qr_image(texte, box=8):
    img = qrcode.make(texte, box_size=box, border=1)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _pied_de_page(params, titre):
    def dessiner(c, doc):
        c.saveState()
        w, _ = doc.pagesize
        c.setStrokeColor(OR)
        c.setLineWidth(0.8)
        c.line(doc.leftMargin, 14 * mm, w - doc.rightMargin, 14 * mm)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS)
        infos = " · ".join(x for x in [params.nom_etablissement, params.adresse, params.telephone,
                                         params.email, params.mentions_legales] if x)
        c.drawString(doc.leftMargin, 10 * mm, infos[:160])
        c.drawRightString(w - doc.rightMargin, 10 * mm, f"{titre} — page {doc.page}")
        c.restoreState()
    return dessiner


def _entete(params, titre_doc, lignes_droite):
    gauche = [Paragraph(params.nom_etablissement.upper(), S_TITRE_ETAB),
              Paragraph(f"Service : {params.service}", S_SOUS_TITRE)]
    for x in (params.adresse, params.telephone and f"Tél. : {params.telephone}", params.email):
        if x:
            gauche.append(Paragraph(x, S_PETIT))
    droite = [Paragraph(titre_doc, S_DOC)] + [Paragraph(l, S_DROITE) for l in lignes_droite]
    t = Table([[_logo_flowable(params), gauche, droite]], colWidths=[26 * mm, 82 * mm, 72 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return [t, Spacer(1, 3 * mm), _filet(), Spacer(1, 5 * mm)]


def _filet():
    t = Table([[""]], colWidths=[180 * mm], rowHeights=[1.2])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), OR)]))
    return t


def _bandeau(texte, largeur=180 * mm):
    t = Table([[Paragraph(texte, S_SECTION)]], colWidths=[largeur])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), VERT),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


# ---------------------------------------------------------------------------
# FACTURE
# ---------------------------------------------------------------------------
def facture_pdf(facture) -> bytes:
    params = Parametres.get()
    tx: Transaction = facture.transaction
    client, abo = tx.client, tx.abonnement
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=20 * mm,
                            title=f"Facture {facture.numero}", author=params.nom_etablissement)
    if tx.statut == Transaction.Statut.ANNULEE:
        statut, couleur = "ANNULÉE", "#B42318"
    elif tx.reste == 0:
        statut, couleur = "PAYÉE", "#0F3D36"
    elif tx.montant_paye > 0:
        statut, couleur = "PARTIELLEMENT PAYÉE", "#B8913A"
    else:
        statut, couleur = "EN ATTENTE DE PAIEMENT", "#B42318"
    el = _entete(params, "FACTURE", [
        f"<b>N° {facture.numero}</b>",
        f"Date : {_dt(facture.date_emission)}",
        f"Transaction : {tx.numero}",
        f'<font color="{couleur}"><b>{statut}</b></font>',
    ])

    # Client
    bloc_client = [
        [Paragraph("<b>Client</b>", S_NORMAL), Paragraph(client.nom_complet, S_GRAS),
         Paragraph("<b>Identifiant</b>", S_NORMAL), Paragraph(client.identifiant, S_NORMAL)],
        [Paragraph("<b>Téléphone</b>", S_NORMAL), Paragraph(client.telephone or "—", S_NORMAL),
         Paragraph("<b>E-mail</b>", S_NORMAL), Paragraph(client.email or "—", S_NORMAL)],
    ]
    t = Table(bloc_client, colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LIGNE), ("BACKGROUND", (0, 0), (-1, -1), VERT_CLAIR),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    el += [_bandeau("INFORMATIONS DU CLIENT"), t, Spacer(1, 5 * mm)]

    # Prestation
    if abo:
        validite = (f"Du {abo.date_debut:%d/%m/%Y} au {abo.date_fin:%d/%m/%Y}"
                    if abo.date_debut != abo.date_fin else f"Le {abo.date_debut:%d/%m/%Y}")
        if abo.est_mensuel:
            seances = ("Illimitées" if abo.seances_total is None
                       else f"{abo.seances_total} ({abo.seances_par_semaine}/semaine)")
        elif abo.type == Formule.Type.HORAIRE and tx.type != Transaction.Type.SUPPLEMENT:
            seances = f"1 séance de {duree_lisible(abo.duree_minutes)}"
        elif tx.type == Transaction.Type.SUPPLEMENT:
            seances = "—"
        else:
            seances = "1"
    else:
        validite, seances = "—", "—"
    entetes = ["Désignation", "Validité", "Séances autorisées", "Qté", "Prix unitaire", "Montant"]
    lignes = [[Paragraph(h, S_SECTION) for h in entetes],
              [Paragraph(tx.designation, S_NORMAL), Paragraph(validite, S_NORMAL), Paragraph(seances, S_NORMAL),
               Paragraph(str(tx.quantite), S_CENTRE), Paragraph(fcfa(tx.prix_unitaire), S_DROITE),
               Paragraph(fcfa(tx.montant_du), S_DROITE)]]
    t = Table(lignes, colWidths=[62 * mm, 34 * mm, 28 * mm, 10 * mm, 22 * mm, 24 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VERT), ("GRID", (0, 0), (-1, -1), 0.5, LIGNE),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 1), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 1), (-1, -1), 6)]))
    el += [_bandeau("PRESTATION"), t, Spacer(1, 4 * mm)]

    # Totaux
    tot = [["Montant total", fcfa(tx.montant_du)], ["Montant payé", fcfa(tx.montant_paye)]]
    if tx.montant_rembourse:
        tot.append(["Remboursé", "– " + fcfa(tx.montant_rembourse)])
    tot += [["Reste à payer", fcfa(tx.reste)], ["Mode de paiement", tx.modes_paiement()]]
    tt = Table(tot, colWidths=[40 * mm, 45 * mm])
    tt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5), ("FONT", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -2), 0.4, LIGNE),
        ("BACKGROUND", (0, 0), (-1, 0), VERT_CLAIR), ("FONT", (1, 0), (1, 0), "Helvetica-Bold", 11),
        ("TEXTCOLOR", (1, -2), (1, -2), ROUGE if tx.reste else VERT), ("FONT", (1, -2), (1, -2), "Helvetica-Bold", 10),
        ("BOX", (0, 0), (-1, -1), 0.8, VERT)]))
    regs = list(tx.reglements.filter(annule=False).select_related("mode", "recu_par"))
    gauche = []
    if regs:
        rows = [["Reçu", "Date", "Mode", "Montant"]] + [
            [r.numero, timezone.localtime(r.date).strftime("%d/%m/%Y %H:%M"),
             r.mode.nom + (f" ({r.reference})" if r.reference else ""), fcfa(r.montant)] for r in regs]
        tr = Table(rows, colWidths=[24 * mm, 24 * mm, 27 * mm, 20 * mm])
        tr.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
                                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (-1, 0), GRIS),
                                ("LINEBELOW", (0, 0), (-1, 0), 0.4, LIGNE), ("ALIGN", (-1, 0), (-1, -1), "RIGHT")]))
        gauche = [Paragraph("<b>Détail des encaissements</b>", S_PETIT), tr]
    t = Table([[gauche, tt]], colWidths=[95 * mm, 85 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    el += [t, Spacer(1, 6 * mm)]

    # Personnel
    coach = tx.coach or (abo.coach if abo else None)
    perso = Table([[Paragraph(f"<b>Réceptionniste :</b> {tx.cree_par.nom_complet if tx.cree_par else '—'}", S_NORMAL),
                    Paragraph(f"<b>Coach responsable :</b> {coach or 'Non applicable'}", S_NORMAL)]],
                  colWidths=[90 * mm, 90 * mm])
    el += [_bandeau("PERSONNEL"), perso, Spacer(1, 5 * mm)]
    if tx.observations:
        el += [Paragraph(f"<b>Observations :</b> {tx.observations}", S_NORMAL), Spacer(1, 4 * mm)]
    if tx.statut == Transaction.Statut.ANNULEE:
        el += [Paragraph(f'<font color="#B42318"><b>Transaction annulée le {_dt(tx.annulee_le)} — motif : '
                         f'{tx.motif_annulation}</b></font>', S_NORMAL), Spacer(1, 4 * mm)]

    # Signatures + cachet
    cachet = ""
    if params.cachet:
        try:
            cachet = Image(params.cachet.path, width=24 * mm, height=24 * mm, kind="proportional")
        except Exception:
            cachet = ""
    sig = Table([
        [Paragraph("Signature du client", S_PETIT), Paragraph("Signature du réceptionniste", S_PETIT),
         Paragraph("Signature du coach", S_PETIT), Paragraph("Cachet WELLNESS HOTEL", S_PETIT)],
        ["", "", "", cachet]], colWidths=[45 * mm] * 4, rowHeights=[6 * mm, 26 * mm])
    sig.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LIGNE), ("INNERGRID", (0, 0), (-1, -1), 0.6, LIGNE),
                             ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 1), (-1, 1), "MIDDLE")]))
    el += [KeepTogether([sig, Spacer(1, 6 * mm),
                         Paragraph(f"<i>{params.mention_remerciement}</i>",
                                   _st("merci", alignment=TA_CENTER, textColor=VERT, fontSize=10))])]

    def premiere(c, d):
        _pied_de_page(params, f"Facture {facture.numero}")(c, d)
        if tx.statut == Transaction.Statut.ANNULEE:
            c.saveState()
            c.setFillColor(colors.Color(0.7, 0.14, 0.1, alpha=0.12))
            c.setFont("Helvetica-Bold", 90)
            c.translate(A4[0] / 2, A4[1] / 2)
            c.rotate(35)
            c.drawCentredString(0, 0, "ANNULÉE")
            c.restoreState()
    doc.build(el, onFirstPage=premiere, onLaterPages=premiere)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# REÇU SIMPLIFIÉ (format ticket 80 mm)
# ---------------------------------------------------------------------------
def recu_pdf(reglement) -> bytes:
    params = Parametres.get()
    tx = reglement.transaction
    lignes = [
        ("titre", params.nom_etablissement.upper()),
        ("centre", params.service),
        ("centre", params.telephone or ""),
        ("sep", ""),
        ("gras", f"REÇU N° {reglement.numero}"),
        ("txt", f"Date : {_dt(reglement.date)}"),
        ("txt", f"Client : {tx.client.nom_complet}"),
        ("txt", f"Identifiant : {tx.client.identifiant}"),
        ("sep", ""),
        ("txt", tx.designation),
        ("txt", f"Facture : {tx.facture.numero}"),
        ("sep", ""),
        ("ligne", ("Montant encaissé", fcfa(reglement.montant))),
        ("ligne", ("Mode", reglement.mode.nom)),
    ]
    if reglement.reference:
        lignes.append(("ligne", ("Référence", reglement.reference)))
    lignes += [("ligne", ("Total facture", fcfa(tx.montant_du))),
               ("ligne", ("Total payé", fcfa(tx.montant_paye))),
               ("ligne", ("Reste à payer", fcfa(tx.reste))),
               ("sep", ""),
               ("txt", f"Reçu par : {reglement.recu_par.nom_complet if reglement.recu_par else '—'}")]
    if reglement.annule:
        lignes.append(("gras", f"ENCAISSEMENT ANNULÉ : {reglement.motif_annulation}"))
    lignes += [("sep", ""), ("centre", "Merci de votre visite !")]

    import textwrap
    rendu = []
    for t, v in lignes:
        if t == "txt":
            rendu += [("txt", x) for x in textwrap.wrap(v, 42)] or [("txt", "")]
        else:
            rendu.append((t, v))
    largeur = 80 * mm
    hauteur = (len(rendu) * 5 + 16) * mm / 1.25
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(largeur, hauteur))
    c.setTitle(f"Reçu {reglement.numero}")
    y = hauteur - 9 * mm
    for t, v in rendu:
        if t == "titre":
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(VERT)
            c.drawCentredString(largeur / 2, y, v)
            c.setFillColor(colors.black)
        elif t == "centre":
            c.setFont("Helvetica", 8)
            c.drawCentredString(largeur / 2, y, v)
        elif t == "gras":
            c.setFont("Helvetica-Bold", 9)
            c.drawString(5 * mm, y, v[:44])
        elif t == "sep":
            c.setDash(1, 2)
            c.line(5 * mm, y + 1.5 * mm, largeur - 5 * mm, y + 1.5 * mm)
            c.setDash()
        elif t == "ligne":
            c.setFont("Helvetica", 8.5)
            c.drawString(5 * mm, y, v[0])
            c.setFont("Helvetica-Bold", 8.5)
            c.drawRightString(largeur - 5 * mm, y, v[1])
        else:
            c.setFont("Helvetica", 8)
            c.drawString(5 * mm, y, v)
        y -= 4 * mm
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# CARTE DE MEMBRE (format carte bancaire 85,6 × 54 mm)
# ---------------------------------------------------------------------------
def carte_membre_pdf(client, abonnement=None) -> bytes:
    params = Parametres.get()
    W, H = 85.6 * mm, 54 * mm
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"Carte de membre {client.identifiant}")
    c.setFillColor(VERT)
    c.roundRect(0, 0, W, H, 3 * mm, stroke=0, fill=1)
    c.setFillColor(OR)
    c.rect(0, H - 13 * mm, W, 0.8 * mm, stroke=0, fill=1)
    # Logo
    if params.logo:
        try:
            c.drawImage(ImageReader(params.logo.path), 4 * mm, H - 11.5 * mm, 9 * mm, 9 * mm,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    else:
        c.setFillColor(OR)
        c.circle(8.5 * mm, H - 7 * mm, 4.2 * mm, stroke=0, fill=1)
        c.setFillColor(VERT)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(8.5 * mm, H - 8.6 * mm, "W")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(15 * mm, H - 6.8 * mm, params.nom_etablissement.upper())
    c.setFont("Helvetica", 6.5)
    c.setFillColor(OR)
    c.drawString(15 * mm, H - 10 * mm, "CARTE DE MEMBRE · " + params.service.upper())
    # Infos
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(5 * mm, H - 21 * mm, client.nom_complet[:30])
    c.setFont("Helvetica", 7)
    y = H - 27 * mm
    infos = [("Identifiant", client.identifiant)]
    if abonnement:
        infos += [("Formule", abonnement.designation.split(" — ")[0]),
                  ("Validité", f"{abonnement.date_debut:%d/%m/%Y} → {abonnement.date_fin:%d/%m/%Y}")]
    infos.append(("Membre depuis", f"{client.date_inscription:%d/%m/%Y}"))
    from reportlab.pdfbase.pdfmetrics import stringWidth
    largeur_max = W - 27 * mm - 29 * mm  # s'arrête avant le QR code
    for k, v in infos:
        c.setFont("Helvetica", 5.8)
        c.setFillColor(OR)
        c.drawString(5 * mm, y, k.upper())
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.white)
        if stringWidth(v, "Helvetica", 7) > largeur_max:
            while v and stringWidth(v + "…", "Helvetica", 7) > largeur_max:
                v = v[:-1]
            v = v.rstrip() + "…"
        c.drawString(29 * mm, y, v)
        y -= 4.6 * mm
    # QR code
    c.setFillColor(colors.white)
    c.roundRect(W - 25 * mm, 5 * mm, 21 * mm, 21 * mm, 1.5 * mm, stroke=0, fill=1)
    c.drawImage(ImageReader(qr_image(client.identifiant)), W - 24 * mm, 6 * mm, 19 * mm, 19 * mm)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(W - 14.5 * mm, 2.2 * mm, "Présentez ce code à la réception")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# RAPPORTS
# ---------------------------------------------------------------------------
def rapport_pdf(titre, sous_titre, colonnes, lignes, totaux=None, auteur="") -> bytes:
    params = Parametres.get()
    buf = BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=20 * mm, title=titre)
    largeur = page[0] - 24 * mm
    entete = Table([[_logo_flowable(params, 16 * mm),
                     [Paragraph(params.nom_etablissement.upper(), S_TITRE_ETAB),
                      Paragraph(params.service, S_SOUS_TITRE)],
                     [Paragraph(titre, _st("rt", fontName="Helvetica-Bold", fontSize=14, leading=17,
                                           textColor=VERT, alignment=TA_RIGHT)),
                      Paragraph(sous_titre, S_DROITE),
                      Paragraph(f"Édité le {_dt(timezone.now())}" + (f" par {auteur}" if auteur else ""), S_PETIT)]]],
                   colWidths=[20 * mm, 100 * mm, largeur - 120 * mm])
    entete.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    filet = Table([[""]], colWidths=[largeur], rowHeights=[1.2])
    filet.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), OR)]))
    st_cell = _st("cell", fontSize=7.8, leading=9.5)
    data = [[Paragraph(c, _st("h", fontName="Helvetica-Bold", fontSize=7.8, leading=9.5, textColor=colors.white))
             for c in colonnes]]
    for l in lignes:
        data.append([Paragraph("" if v is None else str(v), st_cell) for v in l])
    if totaux:
        data.append([Paragraph(f"<b>{'' if v is None else v}</b>", st_cell) for v in totaux])
    if len(data) == 1:
        data.append([Paragraph("Aucune donnée pour les critères choisis.", st_cell)] + [""] * (len(colonnes) - 1))
    t = Table(data, repeatRows=1, colWidths=[largeur / len(colonnes)] * len(colonnes))
    style = [("BACKGROUND", (0, 0), (-1, 0), VERT), ("GRID", (0, 0), (-1, -1), 0.4, LIGNE),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F9F8")])]
    if totaux:
        style.append(("BACKGROUND", (0, -1), (-1, -1), VERT_CLAIR))
    t.setStyle(TableStyle(style))
    doc.build([entete, Spacer(1, 2 * mm), filet, Spacer(1, 4 * mm), t],
              onFirstPage=_pied_de_page(params, titre), onLaterPages=_pied_de_page(params, titre))
    return buf.getvalue()
