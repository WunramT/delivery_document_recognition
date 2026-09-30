# Instrukcja: poprawianie etykiet (PL)

Wszystkie polecenia uruchamia się w katalogu projektu, w kontenerze deweloperskim
(Dev Container) lub w terminalu z zainstalowanym środowiskiem. Wszystko działa lokalnie,
bez internetu.

## 1. Przygotowanie propozycji etykiet i edytora

```
make relabel
```

Polecenie łączy dotychczasowe etykiety z wynikami modelu i dla każdej trasy tworzy folder
`artifacts/relabel/<trasa>_<data>/`, np. `artifacts/relabel/425_21.09.2026/`, z plikami:

- `editor_pl.html` – edytor po polsku (`editor.html` = wersja niemiecka)
- `_annotations.coco.json`, `images/`, `page_types.csv` – kopia danych trasy

Jeśli wytrenowano już nowy model w osobnym folderze, propozycje pochodzą z niego:

```
DOCVAL_ARTIFACTS=artifacts/exp_425 make relabel
```

## 2. Praca w edytorze

`editor_pl.html` otworzyć podwójnym kliknięciem (najlepiej Chrome lub Edge). Po lewej lista
stron (filtr „z propozycjami modelu” / „niesprawdzone”), pośrodku strona z ramkami.

| Czynność | Obsługa |
|---|---|
| Nowa ramka | przeciągnąć na pustym miejscu (klasę wybrać wcześniej klawiszem `1`–`4`) |
| Przesunąć / zmienić rozmiar | kliknąć ramkę i przeciągnąć; przeciągnąć róg lub krawędź |
| Zmienić klasę | zaznaczyć ramkę, potem `1`–`4` |
| Usunąć / cofnąć | `Delete` / `Ctrl+Z` |
| Dokładne przesunięcie | strzałki (`Shift` = 10 px, `Alt` = rozmiar) |
| Strony | `A` / `D` = poprzednia / następna, `Enter` = sprawdzone i dalej |
| Stare etykiety dla porównania | `O` (litera) – szara przerywana linia |
| Powiększenie | `+`, `-`, `0` = do szerokości, albo Ctrl + kółko myszy |
| Typ dokumentu | lista rozwijana u góry, osobno dla każdej strony |

Klasy: `1` podpis, `2` pieczątka, `3` numer trasy, `4` licznik CMR.
Linia przerywana = propozycja modelu, której jeszcze nikt nie poprawiał.

Stan pracy zapisuje się w przeglądarce – można zamknąć stronę i kontynuować później.

## 3. Zasady etykietowania

- Każdy widoczny obiekt dostaje dokładnie jedną ramkę – niczego nie pomijać, niczego nie dublować.
- Ramka ciasno wokół treści (kilka pikseli marginesu), a nie wokół całego pola.
- CMR: nie oznaczać nadrukowanych podpisów/pieczątek w polach 22 i 23.
- **podpis**: tylko odręczny podpis, ciasno wokół tuszu
- **pieczątka**: cały odcisk pieczątki, ciasno wokół odcisku
- **numer trasy**: pełny numer trasy (trasa/data/zakład), ciasno
- **licznik CMR**: „CMR i/n” w całości, ciasno

## 4. Zapisywanie

1. Przycisk **„Zapisz COCO”** → plik `_annotations.coco.json` zapisać w
   `labels/<trasa>_<data>/` (np. `labels/425_21.09.2026/`). Wcześniej zrobić kopię starego
   pliku, np. jako `_annotations.coco.alt.json` w tym samym folderze.
2. Jeśli zmieniono typy dokumentów: dodatkowo **„Zapisz page_types.csv”** do tego samego folderu.
3. Nazwa pliku musi brzmieć dokładnie `_annotations.coco.json` (przeglądarka czasem zapisuje
   w „Pobranych” jako `_annotations.coco (1).json`).
4. Nazwa folderu musi pozostać pełna, np. `425_21.09.2026` – z niej pochodzi numer trasy.

Sprawdzenie pliku:

```
make inspect
```

## 5. Porównanie: stare i nowe etykiety

```
make compare-labels EXPORT=425
```

Wynik: `artifacts/label_compare/425_21.09.2026_pl.html` (po polsku) oraz
`artifacts/label_compare/425_21.09.2026.html` (po niemiecku). Jeden plik z osadzonymi
obrazami – zasady etykietowania, tabela zmian dla każdej klasy, zbliżenia przed/po i wszystkie
zmienione strony obok siebie.

Stare etykiety pochodzą (w tej kolejności) z:

1. `OLD=...` – `make compare-labels EXPORT=425 OLD=sciezka/do/starego.json`
2. kopii w folderze trasy (np. `_annotations.coco.alt.json`)
3. edytora z `make relabel` (zawiera stan sprzed edycji – nie uruchamiać ponownie
   `make relabel` przed porównaniem)

Uwaga: plik zawiera skany z nazwiskami, podpisami i pieczątkami – tylko do użytku wewnętrznego.

## 6. Nowe trenowanie i porównanie wyników

```
DOCVAL_ARTIFACTS=artifacts/exp_nowe make split train export eval
make compare A=artifacts B=artifacts/exp_nowe
```

Raport: `artifacts/exp_nowe/report/report.html` (po niemiecku), porównanie:
`artifacts/exp_nowe/report/compare.md`.
