# Mail à envoyer à DILA pour récupérer le Thésaurus Information Publique

## Destinataires (CC tous pour escalade automatique)

- **À** : `donnees-dila@dila.gouv.fr` (équipe Open Data DILA, contact officiel publié sur dila.gouv.fr/contacts/article/nous-contacter)
- **CC** : `webmestre.vie-publique@dila.gouv.fr`, `etalab@modernisation.gouv.fr`, `contact-dinum@modernisation.gouv.fr`

## Objet

Lien cassé pour le téléchargement du Thésaurus Information Publique (SKOS) — référencé par DILA depuis mars 2020

## Corps du mail

> Bonjour,
>
> Je vous écris au sujet du **Thésaurus Information Publique** annoncé par
> la DILA dans une publication officielle datée du 3 mars 2020 ("Nouveau
> référentiel d'indexation : Thésaurus Information Publique"), présenté
> comme un référentiel de 6000 termes structurés en 26 domaines, accessible
> au format SKOS, et destiné à la réutilisation publique conformément à la
> Licence Ouverte 2.0 (Etalab).
>
> **Le lien de téléchargement publié dans cette annonce renvoie une erreur 404.**
> Aucune URL alternative ne semble disponible : ni sur vie-publique.fr, ni sur
> data.gouv.fr (recherche infructueuse), ni dans le répertoire bulk
> echanges.dila.gouv.fr/OPENDATA/. La page de description elle-même bloque
> les téléchargements automatisés via une protection JavaScript.
>
> Conformément à la loi République Numérique du 7 octobre 2016 (codifiée
> aux articles L321-1 et suivants du Code des relations entre le public et
> l'administration), et à l'obligation de mise à disposition gratuite et
> réutilisable des informations publiques sous Licence Ouverte 2.0, je vous
> remercie de bien vouloir :
>
> 1. **Restaurer l'URL de téléchargement direct** du fichier SKOS, ou
> 2. **Publier une nouvelle URL stable**, idéalement via le portail
>    data.gouv.fr ou le répertoire bulk echanges.dila.gouv.fr/OPENDATA/
>    pour une accessibilité durable et programmatique.
>
> J'utilise ce thésaurus dans le cadre du projet open-source
> **justicelibre.org**, qui vise à rendre la jurisprudence française
> accessible gratuitement. Une indexation enrichie par votre référentiel
> officiel permettrait d'améliorer significativement la pertinence des
> recherches juridiques pour des dizaines de milliers d'utilisateurs
> (justiciables, étudiants en droit, journalistes, associations, etc.).
>
> Je reste à votre disposition pour toute information complémentaire.
>
> Bien cordialement,
> [Ton prénom + nom]
> Mainteneuse du projet justicelibre.org
> contact@justicelibre.org

## Si pas de réponse sous 1 mois

Saisine **CADA** (Commission d'accès aux documents administratifs) :
- Formulaire en ligne : https://www.cada.fr/contact
- Référence à mentionner : "Refus implicite de communication d'un document
  administratif réutilisable au titre du Code des relations entre le public
  et l'administration (CRPA), articles L321-1 et suivants"
- La CADA a 1 mois pour rendre un avis. Avis positif → DILA est obligée de
  publier sous 2 mois.

## Plan B (si DILA refuse / ne répond pas)

Scraping via Playwright stealth :
- Effort : ~5-6h dev + 1-2h scraping
- Risque : ban IP Cloudflare (vie-publique = Cloudflare actif)
- Cible : crawler la page /collection/discours-publics ou similaire qui
  expose le thésaurus en navigation HTML
