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
| Nowa ramka | przeciągnąć na pustym miejscu (klasę wybrać wcześniej klawiszem `1`–`7`) |
| Przesunąć / zmienić rozmiar | kliknąć ramkę i przeciągnąć; przeciągnąć róg lub krawędź |
| Zmienić klasę | zaznaczyć ramkę, potem `1`–`7` |
| Usunąć / cofnąć | `Delete` / `Ctrl+Z` |
| Dokładne przesunięcie | strzałki (`Shift` = 10 px, `Alt` = rozmiar) |
| Strony | `A` / `D` = poprzednia / następna, `Enter` = sprawdzone i dalej |
| Stare etykiety dla porównania | `O` (litera) – szara przerywana linia |
| Powiększenie | `+`, `-`, `0` = do szerokości, albo Ctrl + kółko myszy |
| Typ dokumentu | lista rozwijana u góry, osobno dla każdej strony |

Klasy: `1` podpis, `2` pieczątka, `3` numer trasy, `4` licznik CMR, `5` numer TA, `6` nr dowodu dostawy, `7` numer strony. Instrukcja dla wybranej klasy jest wyświetlana pod listą klas.
Linia przerywana = propozycja modelu. **Przy zapisie propozycje stają się etykietami**: pasujące zostawić, błędne usunąć (`Delete`), niedokładne poprawić. `Enter` (sprawdzone) zamienia pozostałe propozycje na linię ciągłą.

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

## 7. Kontrola trasy w praktyce (produkcja)

Cały nieposortowany stos trasy skanuje się jeden raz. Aplikacja automatycznie sprawdza część
organizacyjną (typ dokumentu, numer trasy, licznik CMR, duplikaty, kompletność). Osoba
sprawdzająca decyduje na jednej stronie o wszystkich pieczątkach i podpisach – **ostatnie słowo
należy zawsze do niej**. Pełny opis procesu (po niemiecku): `docs/PROZESS.md`.

```
make process SCANS=skany/503_01.09.2026.pdf            # PDF, obraz albo folder
make process SCANS=skany/trasa503/ TOUR=503_01.09.2026  # numer trasy, jeśli nie ma go w nazwie
```

Wynik: `artifacts/process/<trasa>/pruefung_pl.html` – otworzyć podwójnym kliknięciem (Chrome/Edge).

1. **Organizacja** – wynik automatyczny (✓ / ✗ / ! wskazówka) i kolejność CMR 1..n
   (brakujący numer na czerwono, duplikat na żółto).
2. **Do wyjaśnienia** – tylko jeśli są: wybrać typ dokumentu, wpisać nr CMR `i/n` lub numer trasy.
3. **Podpis i pieczątka** – karta dla każdego CMR / dowodu dostawy. Dla każdego obiektu
   „jest” / „brak” (wstępnie ustawione według modelu, przy „model niepewny” puste), potem
   **„Potwierdź”**. Kliknięcie obrazu = cała strona. Klawisze: `J`/`K` zmiana karty, `1` podpis,
   `2` pieczątka, `A` archiwizować, `Enter` potwierdź + dalej, spacja = cała strona.

Wpisać imię i nazwisko w polu „Sprawdzający”, **„Zapisz decyzję”** → plik `entscheidung.json`
umieścić w folderze strony kontrolnej. Następnie:

```
make finalize RUN=503_01.09.2026_4000
```

W `freigabe/`: `CMR_<trasa>.pdf` (posortowane 1..n, bez duplikatów), `LS_<trasa>.pdf`, szkice
e-maili `.eml` do `leopol-cmr@polipol.de` / `leopol-ls@polipol.de` (otworzyć w Outlooku i wysłać)
oraz `protokoll_pl.txt` z wynikiem KOMPLETNE/OTWARTE, listą „Do zrobienia” (Polilogistics,
dokument zastępczy, inna trasa, ZCHECKLSARCHIV następnego dnia) i kolejnością papieru do archiwum.

Odczyt numerów TA z listy załadunkowej nie jest jeszcze zweryfikowany – pojawia się tylko jako
wskazówka. Liczbę TA na liście załadunkowej nadal sprawdza osoba.

## 8. Etykietowanie nowych skanów (`make label-scans`)

Skany zostają lokalnie, nie trafiają do repozytorium.

```
make process SCANS=skany/503_01.09.2026.pdf
make label-scans RUN=503_01.09.2026_4000
```

Wynik: `artifacts/label_scans/503_01.09.2026/` – ten sam układ co eksport etykiet, ramki modelu jako
propozycje. Folder skopiować do `labels/503_01.09.2026/`, otworzyć `editor_pl.html`, sprawdzić ramki
i dodać nowe klasy:

- `5` **numer TA**: lista załadunkowa – „Zlecenie” i numer TA pod nim w jednej ramce, jedna ramka na
  wiersz; CMR – wszystkie numery TA po kolei (x, y, z) w jednej ramce; dowód dostawy – nie oznaczać
- `6` **nr dowodu dostawy**: „Lieferschein XXXXXXXX” (pierwsza strona, u góry pośrodku) lub
  „Lieferschein (XXXXXXXX)” (kolejne strony, u góry po lewej)
- `7` **numer strony**: dowód dostawy u dołu po prawej „Seite 1/2”, lista załadunkowa u góry po prawej „2/6”

„Zapisz COCO” do `labels/503_01.09.2026/`, potem `make inspect split train export eval`.

## 9. Nowe klasy we wszystkich trasach (`make relabel-model`)

Gdy jedna trasa jest w pełni oznaczona nowymi klasami (zapisana w edytorze):

```
make relabel-model    # model wzorcowy tylko z tras oznaczonych wszystkimi klasami
make relabel          # propozycje dla wszystkich tras, także dla trasy wzorcowej
```

Trasa wzorcowa: każda strona dostaje propozycje od modelu, który jej nie widział – tak widać
zapomniane ramki; dodawane są tylko brakujące ramki, poprawione ramki zostają. Pozostałe trasy:
propozycje dla nowych klas (linia przerywana). Przejrzeć, poprawić, „Zapisz COCO”. Każda zapisana
trasa staje się kolejnym wzorcem – powtarzać `make relabel-model relabel`, aż wszystkie trasy będą
gotowe. Potwierdzenia zbiorcze (Hermes/DHL) oznaczyć u góry jako typ dokumentu
„potwierdzenie zbiorcze”.
