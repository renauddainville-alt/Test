"""Generate a FICTITIOUS French tender PDF for testing the analyser.

The contracting authority, reference and all content are invented.
Run: python examples/make_sample_tender.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).with_name("sample_tender_fr.pdf")

CONTENT = [
    ("title", "CAHIER SPÉCIAL DES CHARGES"),
    ("p", "Cahier spécial des charges n° RFT-IT-2027-014"),
    ("p", "Objet du marché : Services managés d'infrastructure IT et support utilisateurs"),
    ("p", "Pouvoir adjudicateur : Régie Fictive des Transports (RFT), Rue de l'Exemple 1, 1000 Bruxelles"),
    ("p", "Procédure ouverte avec publicité européenne"),
    ("p", "Codes CPV : 72250000-2 (services de maintenance des systèmes et services d'assistance), "
          "72611000-6 (services d'assistance informatique)"),
    ("p", "Montant estimé du marché : 4.800.000 € HTVA"),
    ("h", "1. DISPOSITIONS ADMINISTRATIVES"),
    ("h", "1.1 Durée du marché"),
    ("p", "Durée du marché : 48 mois à compter de la notification, reconductible une fois 12 mois."),
    ("p", "Le présent marché est soumis à la loi du 17 juin 2016 relative aux marchés publics."),
    ("h", "1.2 Calendrier"),
    ("p", "Date de publication : 05/12/2026"),
    ("p", "Séance d'information : 08/01/2027 à 10h00 dans les locaux du pouvoir adjudicateur."),
    ("p", "Date limite pour les questions : 15/01/2027 à 12h00"),
    ("p", "Date limite de dépôt des offres : 29 janvier 2027 à 11h00"),
    ("p", "Ouverture des offres : 29/01/2027 à 11h30"),
    ("p", "Début des prestations prévu : 01/06/2027"),
    ("h", "1.3 Lots"),
    ("p", "Lot 1 : Gestion du datacenter et des serveurs"),
    ("p", "Lot 2 : Support utilisateurs (service desk et support sur site)"),
    ("p", "Lot 3 : Sécurité opérationnelle (SOC)"),
    ("h", "1.4 Dépôt des offres"),
    ("p", "L'offre doit être introduite exclusivement via la plateforme e-Procurement, à peine de nullité."),
    ("p", "L'offre doit être signée au moyen d'une signature électronique qualifiée. "
          "Le délai d'engagement est de 180 jours calendrier à compter de la date limite de réception des offres."),
    ("p", "L'offre devra être rédigée en français ou en néerlandais."),
    ("h", "2. CRITÈRES D'EXCLUSION ET DE SÉLECTION"),
    ("h", "2.1 Exclusion"),
    ("p", "Le soumissionnaire ne doit pas se trouver dans une des situations d'exclusion visées aux articles 67 à 69 "
          "de la loi. Le soumissionnaire doit être en règle avec ses obligations en matière de dettes sociales et fiscales."),
    ("h", "2.2 Capacité économique et financière"),
    ("p", "Le soumissionnaire doit avoir réalisé un chiffre d'affaires annuel d'au minimum 10.000.000 € "
          "au cours de chacun des trois derniers exercices. Le soumissionnaire joint à son offre une déclaration "
          "relative au chiffre d'affaires des trois derniers exercices."),
    ("h", "2.3 Capacité technique et professionnelle"),
    ("p", "Le soumissionnaire doit fournir au minimum trois références de marchés similaires exécutés au cours "
          "des trois dernières années, dont au moins une pour un client du secteur des transports, à peine d'exclusion."),
    ("p", "Le soumissionnaire doit fournir une copie de son certificat ISO 27001 en cours de validité."),
    ("p", "Une certification ISO 20000 est un atout."),
    ("h", "3. CRITÈRES D'ATTRIBUTION"),
    ("p", "Les offres seront évaluées sur base des critères suivants :"),
    ("p", "Critère 1 : Prix : 40 %"),
    ("p", "Critère 2 : Qualité de la méthodologie et du plan de transition : 30 %"),
    ("p", "Critère 3 : Qualité de l'équipe proposée : 20 %"),
    ("p", "Critère 4 : Approche en matière de durabilité : 10 %"),
    ("break", ""),
    ("h", "4. PRESCRIPTIONS TECHNIQUES"),
    ("h", "4.1 Niveaux de service"),
    ("p", "Le prestataire doit garantir une disponibilité des systèmes critiques de 99,9 % par mois. "
          "Le temps de réponse pour un incident de priorité 1 doit être inférieur à 30 minutes, 24h/24 et 7j/7."),
    ("p", "En cas de non-respect des SLA, une pénalité de 1 % de la facture mensuelle sera appliquée par tranche "
          "de 0,1 % de disponibilité manquante."),
    ("h", "4.2 Sécurité"),
    ("p", "Le prestataire doit se conformer aux exigences de la directive NIS2 et du RGPD. "
          "Les données doivent être hébergées exclusivement dans l'Union européenne."),
    ("p", "Le personnel affecté au lot 3 devra disposer d'une habilitation de sécurité de niveau « confidentiel »."),
    ("h", "4.3 Équipe"),
    ("p", "Le chef de projet doit disposer d'au moins 10 années d'expérience et d'une certification ITIL 4. "
          "Le soumissionnaire joint à son offre le CV de chaque membre clé de l'équipe."),
    ("p", "Les agents du service desk doivent être bilingues français et néerlandais. "
          "La connaissance de l'anglais est souhaitée."),
    ("h", "4.4 Prix"),
    ("p", "Le soumissionnaire doit compléter l'inventaire des prix joint en annexe. Toute omission dans l'inventaire "
          "sera considérée comme une irrégularité substantielle."),
]


def main() -> Path:
    styles = getSampleStyleSheet()
    flow = []
    for kind, text in CONTENT:
        if kind == "break":
            flow.append(PageBreak())
        elif kind == "title":
            flow += [Paragraph(text, styles["Title"]), Spacer(1, 8)]
        elif kind == "h":
            flow += [Spacer(1, 6), Paragraph(text, styles["Heading2"])]
        else:
            flow += [Paragraph(text, styles["BodyText"]), Spacer(1, 4)]
    SimpleDocTemplate(str(OUT), pagesize=A4, title="Exemple fictif de CSC").build(flow)
    return OUT


if __name__ == "__main__":
    print(main())
