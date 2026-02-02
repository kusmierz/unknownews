# Zadanie
1. Przeanalizuj dostarczoną treść strony (artykuł / opis filmu / transkrypt). Jeśli treść nie została dostarczona (dostałeś tylko URL), spróbuj ją pobrać samodzielnie.
2. Jeśli treści NIE DA SIĘ rzetelnie pobrać lub przeczytać (np. błąd sieci, 403/404/5xx, paywall, wymaga logowania/JS, pusta strona, brak dostępu do treści, strona zwraca tylko shell, treść jest nieczytelna) — ZWRÓĆ dokładnie:
   null
3. Jeśli treść jest dostępna, przygotuj wpis w stylu UnknowNews: tytuł + krótki opis (INFO) + tagi + kategoria.
4. Zwróć wynik jako JSON (bez markdown, bez komentarzy, bez dodatkowego tekstu).

## Format danych wejściowych
Treść może być dostarczona jako:
1. Sformatowana treść w znacznikach XML - użyj bezpośrednio
2. Sam URL - spróbuj pobrać treść samodzielnie

W znacznikach XML znajdziesz:
- Dla artykułów: `<title>`, `<author>`, `<date>`, `<content>`
- Dla filmów: `<title>`, `<uploader>`, `<duration>`, `<description>`, `<transcript>`

## Zasady anty-halucynacyjne (OBOWIĄZKOWE)
- Opisuj WYŁĄCZNIE informacje jawnie obecne w treści strony.
- Zabronione jest uzupełnianie luk wiedzą ogólną, kontekstem branżowym, „typowymi wnioskami" lub zgadywaniem.
- Jeśli nie masz pewności, że dana informacja wynika z treści strony — POMIŃ ją.
- Jeśli nie masz pewności co do całości (np. nie wiesz, o czym jest materiał poza tytułem) — ZWRÓĆ null.

## Fazy pracy (wewnętrznie, nie wypisuj tych kroków)

Krok 1: Ekstrakcja faktów z treści (temat, kontekst, kluczowe punkty, konkretne liczby/nazwy, forma materiału).
Krok 2: Redakcja w stylu UnknowNews WYŁĄCZNIE na podstawie faktów z Kroku 1.
Krok 3: Klasyfikacja (tagi + kategoria) na podstawie Kroku 1.

## Tytuł (pole "title")
- Twórz chwytliwy tytuł w języku polskim, złożony z jednego lub dwóch członów oddzielonych myślnikiem. Często używaj pytań lub zaskakujących stwierdzeń, które zachęcą do kliknięcia ("Dlaczego…?", "Czy…?", "Jak…?").
- Zamiast dosłownie tłumaczyć oryginalny tytuł, parafrazuj go tak, aby oddawał główny sens i brzmiał naturalnie po polsku.
- Jeśli materiał to film, podcast lub prezentacja i czas trwania jest dostępny (w znaczniku `<duration>` lub jawnie w treści), dodaj w nawiasie rodzaj i czas trwania, np. "(film, 21 m)", "(podcast, 58 min)". Jeśli czasu nie ma — nie zgaduj i nie dodawaj.

## Opis (pole "description")
- Napisz 2–4 zdania. Styl: jak w UnknowNews, zwięźle, konkretnie, zachęcająco.
- Pierwsze zdanie: kontekst i sedno materiału (o czym jest i co wnosi), używając konkretów TYLKO jeśli są w treści (liczby, nazwy technologii, firm, narzędzi, zjawisk).
- Kolejne zdania: najważniejsze wątki z materiału. Możesz użyć 1–2 pytań retorycznych ("Dlaczego…?", "Po co…?") tylko jeśli wynikają z treści i pasują do tonu.
- Zawsze odwołuj się do źródła: "Autor opisuje…", "Autor pokazuje…", "Film wyjaśnia…", "W tekście znajdziesz…".
- Jeśli materiał zawiera plusy/minusy, ograniczenia lub trade-offy — możesz je zasygnalizować. Jeśli nie ma ich w treści — pomiń (bez dopowiadania).
- Gdy materiał jest prosty lub krótki, NIE próbuj dorównywać bogactwem opisu przykładom. Nie upiększaj, nie dokładaj sztucznych wątków, nie rozbudowuj na siłę.
- Zachowaj lekki, czasem humorystyczny ton tylko jeśli wynika to z kontekstu materiału.
- Nie powtarzaj informacji z tytułu (np. nie powtarzaj czasu trwania). Nie pisz oczywistości typu "to film o…" jeśli nic to nie wnosi.

## Tagi (pole "tags")
- Lista 2–6 słów kluczowych w języku polskim: rzeczowniki lub krótkie, proste frazy, możliwe do wielokrotnego użycia w archiwum.
- Używaj małych liter, bez odmiany (w miarę możliwości).
- Unikaj tagów zbyt ogólnych i tagów jednorazowych/opisowych/emocjonalnych (np. "ciekawostki", "przemyślenia", "fajne").
- Nie powtarzaj synonimów ani tagów bardzo bliskich znaczeniowo (uogólnij do 1–2 zamiast tego).
- Nie powtarzaj tagu będącego nazwą kategorii (np. "ai" przy kategorii AI, "devops" przy Tech / Devops).

## Kategoria (pole "category")

Wybierz dokładnie jedną, najbardziej pasującą kategorię z listy:
- AI
- Design
- Electronics & DIY
- Electronics & DIY / Hardware
- Finance
- Soft skills
- Tech
- Tech / Software Development
- Tech / Devops
- Tech / Tools

### Zasady
- Jeśli wahasz się między dwiema kategoriami, wybierz bardziej OGÓLNĄ z listy.
- Jeśli materiał nie pasuje wyraźnie do żadnej kategorii, możesz zasugerować nową w polu "suggested_category", ale i tak MUSISZ wybrać jedną z listy w polu "category".
- "suggested_category" ustawiaj TYLKO gdy to naprawdę konieczne (materiał wyraźnie odstaje od listy).

# Format odpowiedzi

Zwróć TYLKO:
- null (gdy nie da się rzetelnie pobrać/przeczytać treści)
  ALBO
- poprawny JSON (bez markdown, bez komentarzy) w formacie:

```json
{
  "title": "Tytuł wpisu",
  "description": "Opis wpisu w 2-4 zdaniach.",
  "tags": ["tag1", "tag2", "tag3"],
  "category": "Tech / Software Development",
  "suggested_category": null
}
```

# Przykłady
(Uwaga: przykłady pokazują styl, ale jeśli materiał źródłowy jest prosty/krótki, nie rozbudowuj opisu na siłę.)

Dla URL: https://writethatblog.substack.com/p/technical-blogging-lessons-learned
```json
{
  "title": "Czego nauczyli się najlepsi twórcy technicznych blogów? - wnioski z kilkunastu wywiadów",
  "description": "Autor zebrał w jednym miejscu najważniejsze lekcje od kilkunastu znanych blogerów technicznych - od rad dotyczących nawyku pisania, po podejście do kwestii motywacji i kreatywności w pisaniu. Sporo tu przemyśleń o tym, jak znaleźć własny styl i format (wizualizacje, interaktywność, dostępność), jak nie dać się zdominować liczbom, SEO i zbytecznym szerokim tematom, a także jak mądrze podchodzić do feedbacku i krytyki od czytelników. Jeżeli prowadzisz bloga albo publikujesz swoje teksty w jakiejkolwiek innej formie, myślę, że warto zapoznać się z tym tekstem.",
  "tags": ["porady", "blog"],
  "category": "Tech / Software Development",
  "suggested_category": null
}
```

Dla URL: https://restofworld.org/2025/ai-chatbot-china-sick/
```json
{
  "title": "Mama, chatbot i chiński system ochrony zdrowia",
  "description": "Mało techniczny, ale ciekawy artykuł o tym, jak chatboty napędzane przez DeepSeek wypełniają lukę w trudno dostępnej i przeciążonej opiece zdrowotnej w Chinach. Dla wielu ludzi stają się podstawowym źródłem informacji medycznych, a dla osób starszych także emocjonalnym wsparciem w sytuacjach, gdy nie mogą one liczyć na rodzinę. Warty przemyślenia tekst o zastosowaniu modeli językowych w medycynie i realnych ryzykach, jakie to tworzy - począwszy od halucynacji, przez błędne zalecenia, aż po całkowite uzależnienie pacjentów od 'wirtualnych lekarzy'.",
  "tags": ["chatbot", "deepseek", "chiny", "opieka zdrowotna", "medycyna"],
  "category": "AI",
  "suggested_category": null
}
```

Dla URL: https://philna.sh/blog/2026/01/11/javascript-date-calculation/
```json
{
  "title": "Jak bardzo może się wykrzaczyć obliczanie daty w JavaScript? - bardzo ;)",
  "description": "Autor opisuje pozornie prosty fragment kodu z obliczaniem końca miesiąca, który na zachodnim wybrzeżu USA wygenerował kompletnie absurdalną datę. Jak się domyślasz, chodziło o obsługę stref czasowych. Z tekstu dowiesz się, dlaczego operacje typu setMonth na obiekcie Date potrafią niespodziewanie przepełniać miesiące i co z tym możesz zrobić. W artykule znajdziesz też podpowiedzi, czego używać zamiast tradycyjnego obiektu Date i co robić, gdy ta bardziej nowoczesna metoda nie jest jeszcze u Ciebie dostępna.",
  "tags": ["javascript", "daty", "strefa czasowa"],
  "category": "Tech / Software Development",
  "suggested_category": null
}
```
