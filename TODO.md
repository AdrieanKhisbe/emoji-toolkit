# TODO

Things to do in the repo reforge

- [x] Add readme
- [x] add gitignore
- [x] add poetry
- [x] regenerate script (attention apple change)
- [x] rewrite tests with pytest
- [x] dataset in resources
- [x] spec the cli (install and display) — [agreed specification](docs/cli-spec.md)
- [x] implement the cli — [commands](docs/cli.md), [resource releases](docs/resource-releases.md)
- [ ] review docs folder and README (disclammer dev )
- [ ] Update the name
- [ ] See the licence
- [ ] Check the packaging
- [ ] Brew formula


------
## Notes recherches
### Fetcher script need to be review
Liens
- https://unicode.org/emoji/charts/emoji-list.html
- https://unicode.org/emoji/charts/full-emoji-list.html n'a plus les version d'apple ni des autres vendors
- https://web.archive.org/web/20220310222859/https://unicode.org/emoji/charts/full-emoji-list.html (ancienne page avec les vendors)
- rework to rely on https://emojipedia.org/apple (et probablement serveurs interne)


### Proto spec for cli

The cli should do two main things:
- manage the installation of the resources `emoji install [--vendor apple]`
  - files should be saved in .config/emojies/data-images
  - installation vendor per vendor. user should be prompted if no argument provided
  - files should be retrieved from github repo resources/dataset
  - files should be read only
  - spaces should be replace with _ in filename
  - along the png file, a .url should be saved with the data-url
  - if more than one vendor install, there should be one set
- serve this resources (either data-uri either image file): `emoji :emoji-code:`
  - --default-skin-tone can be configured and should be applied. `--skin-tone` should be supported
  - optional --vendor option si plusieurs vendors
  - nom de l'émoji supporte les deux point, leur abscence. :grinning: et est agnostique entre "-" et "_" :wind_face: :wind-face:
  - `--url` pour avoir la data url, `--url-file` le chemin du fichier. par default le png est servir
  - should fail and invite to set up if dataset not installed

Notes:
- utiliser la lib `click` sauf si une meilleur est proposée
- utilise des emojis pour décorer les messages et prompts

Extra:
- une option `--size` pourrait etre introduit dans un second temps pour les dataurls. avec encodage à la volée
- ptetre que dans un second temps des customs emoji seront supportée
- possibilité de supprimer un vendor
- install no option install the OS, avec un disclaming default xwarning or validation
- improved list with emoji or not
- autocompletion utils
- `--use-as-default` for vendor install
