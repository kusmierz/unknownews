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
- Dla filmów: `<title>`, `<uploader>`, `<duration>`, `<chapters>`, `<tags>`, `<description>`, `<transcript>`

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
- Jeśli materiał to film, podcast lub prezentacja i czas trwania jest dostępny (w znaczniku `<duration>`), dodaj w nawiasie rodzaj i czas trwania w tytule, np. "(film, 54m)", "(podcast, ~1.5h)".

WAŻNE:
- Czas trwania dodaj TYLKO w tytule, NIE w opisie
- Użyj dokładnie formatu z tagu <duration> (np. "54m", "~1.5h", "2h")
- Jeśli czasu nie ma — nie zgaduj i nie dodawaj

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
- Lista 2–6 słów kluczowych w języku angielskim: rzeczowniki lub krótkie, proste frazy, możliwe do wielokrotnego użycia w archiwum.
- Używaj małych liter, bez odmiany (w miarę możliwości).
- Unikaj tagów zbyt ogólnych i tagów jednorazowych/opisowych/emocjonalnych (np. "curiosities", "thoughts", "cool").
- Nie powtarzaj synonimów ani tagów bardzo bliskich znaczeniowo (uogólnij do 1–2 zamiast tego).
- Nie powtarzaj tagu będącego nazwą kategorii (np. "ai" przy kategorii AI, "devops" przy Tech / Devops).

## Kategoria (pole "category")

Wybierz DOKŁADNIE jedną kategorię główną (top-level) z listy poniżej.
Następnie wybierz DOKŁADNIE jedną subkategorię z obrębie tej kategorii (pole "subcategory").

### Lista kategorii i subkategorii

- AI & ML
  - LLMs & Prompting
  - Agents & Tooling
  - Eval/Inference/Serving
  - AI Industry

- Software Engineering
  - Architecture
  - Backend
  - Frontend
  - Testing/Quality
  - Performance
  - Languages

- Data Systems
  - SQL/DB Internals
  - Data Modeling
  - Caching/Queues
  - Analytics
  - Search/Vector

- Infra & Platforms
  - Containers
  - Linux
  - Networking
  - Cloud
  - Observability
  - SRE/On-call
  - Email/DNS

- Security
  - AppSec
  - CloudSec
  - AI Security
  - Threats/Incidents
  - Privacy

- Product & Design
  - UX
  - UI
  - Research
  - Product Strategy
  - Discovery/Prioritization

- Career & Leadership
  - Interviews
  - Communication/Collaboration
  - Management
  - Productivity
  - Decision-Making

- Business & Money
  - Personal Finance
  - Investing
  - Entrepreneurship
  - Real Estate
  - Taxes

- Hardware & Systems
  - Raspberry Pi/MCUs
  - Electronics
  - Batteries/Power
  - Repair/Reverse
  - Home Lab

- Tools & Workflows
  - CLI
  - Git
  - Editors/IDE
  - Automation
  - Self-hosted tools
  - Templates/Playbooks

- Science & Culture
  - Science explainers
  - Society/Policy
  - History of tech
  - General knowledge

- Misc / Inbox
  - Uncategorized

### Zasady wyboru

1) Wybierz kategorię po tym, “o czym to jest NAJBARDZIEJ”, a nie po tym, jakie technologie są wspomniane pobocznie.

2) Jeśli wahasz się między:
   - Tools & Workflows vs Infra & Platforms:
     - jeśli to o usprawnieniu pracy (narzędzie, workflow, konfiguracja środowiska) → Tools & Workflows
     - jeśli to o uruchamianiu/utrzymaniu systemów (serwery, sieci, kontenery, produkcja, DNS/email) → Infra & Platforms

3) Security ma pierwszeństwo, gdy głównym tematem jest atak/obrona/podatność/eksfiltracja:
   - prompt injection, model jailbreak, agent security → Security / AI Security
   - DMARC/SPF/DKIM jako konfiguracja poczty → Infra & Platforms / Email/DNS
   - ale DMARC jako ochrona przed spoofingiem (ujęcie stricte security) → Security / Threats/Incidents

4) AI & ML wybieraj wtedy, gdy AI jest rdzeniem materiału (LLM, agenci, inference, eval).  
   Jeśli AI jest tylko narzędziem użytym “przy okazji”, wybierz domenę (np. Software Engineering).

5) Jeśli materiał nie pasuje wyraźnie do żadnej kategorii:
   - ustaw category = "Misc / Inbox" oraz subcategory = "Uncategorized"
   - tylko jeśli to częsty typ treści i wyraźnie brakuje miejsca w taksonomii, dodaj pole "suggested_category"

6) "suggested_category" ustawiaj TYLKO gdy to naprawdę konieczne (materiał wyraźnie odstaje i będzie wracał regularnie).
   Mimo to zawsze MUSISZ wybrać jedną kategorię z listy oraz jedną subkategorię.

### Dodatkowe wskazówki spójności (żeby to działało miesiącami)

- Jeśli materiał dotyczy baz danych i jest techniczny (indeksy, query planner, internals) → Data Systems / SQL/DB Internals.
- Jeśli to o planowaniu pracy, komunikacji, 1:1, feedbacku, konfliktach → Career & Leadership.
- Jeśli to ogólne ciekawostki, popularnonaukowe wyjaśnienia, “why is the sky blue?” → Science & Culture.

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
  "tags": ["blogging", "writing"],
  "category": "Software Development",
  "suggested_category": null
}
```

Dla URL: https://restofworld.org/2025/ai-chatbot-china-sick/
```json
{
  "title": "Mama, chatbot i chiński system ochrony zdrowia",
  "description": "Mało techniczny, ale ciekawy artykuł o tym, jak chatboty napędzane przez DeepSeek wypełniają lukę w trudno dostępnej i przeciążonej opiece zdrowotnej w Chinach. Dla wielu ludzi stają się podstawowym źródłem informacji medycznych, a dla osób starszych także emocjonalnym wsparciem w sytuacjach, gdy nie mogą one liczyć na rodzinę. Warty przemyślenia tekst o zastosowaniu modeli językowych w medycynie i realnych ryzykach, jakie to tworzy - począwszy od halucynacji, przez błędne zalecenia, aż po całkowite uzależnienie pacjentów od 'wirtualnych lekarzy'.",
  "tags": ["chatbot", "deepseek", "healthcare", "china"],
  "category": "AI",
  "suggested_category": null
}
```

Dla URL: https://philna.sh/blog/2026/01/11/javascript-date-calculation/
```json
{
  "title": "Jak bardzo może się wykrzaczyć obliczanie daty w JavaScript? - bardzo ;)",
  "description": "Autor opisuje pozornie prosty fragment kodu z obliczaniem końca miesiąca, który na zachodnim wybrzeżu USA wygenerował kompletnie absurdalną datę. Jak się domyślasz, chodziło o obsługę stref czasowych. Z tekstu dowiesz się, dlaczego operacje typu setMonth na obiekcie Date potrafią niespodziewanie przepełniać miesiące i co z tym możesz zrobić. W artykule znajdziesz też podpowiedzi, czego używać zamiast tradycyjnego obiektu Date i co robić, gdy ta bardziej nowoczesna metoda nie jest jeszcze u Ciebie dostępna.",
  "tags": ["javascript", "date", "timezone"],
  "category": "Software Development",
  "suggested_category": null
}
```

Dla URL: https://poledialogu.org.pl/wp-content/uploads/2026/01/Sadura-et-al.-2025-Wiem-ze-to-manipulacja-ale-i-tak-sie-denerwuje-Polacy-w-epoce-dezinformacji.-Raport-z-badan-i-re.pdf
```json
{
  "title": "'Wiem, że to manipulacja, ale i tak się denerwuję' - raport (PDF, 101 stron)",
  "description": "Raport opiera się na badaniu przeprowadzonym na niemal 1400 respondentach i przedstawia ciekawe wnioski dotyczące dezinformacji. Szacuje się, że około 84% Polaków zetknęło się z tym zjawiskiem w ciągu ostatniego roku, a niemal każdy z badanych uwierzył w co najmniej jedną fałszywą wiadomość. Zaufanie do mediów w naszym kraju spadło też do jednego z najniższych poziomów w całej Europie. Ciekawe jest to, że Polacy całkiem dobrze radzą sobie z rozpoznawaniem manipulacji podczas testów, ale zupełnie nie przekłada się to na kontakt z manipulacją w życiu codziennym. Sama świadomość manipulacji również nie przekłada się na praktykę. Pomimo tego, że ludzie wiedzą, że mogą być manipulowani, fake newsy i tak mogą wpłynąć na zmianę ich poglądów. Interesujący raport, wart przemyślenia.",
  "tags": ["disinformation", "prebunking", "debunking", "climate policy", "ets2", "media literacy"],
  "category": "Science & Society",
  "suggested_category": null
}
```

Dla URL: https://newsletter.techworld-with-milan.com/p/you-can-code-only-4-hours-per-day
```json
{
  "title": "Dlaczego powinieneś programować tylko przez 4 godziny dziennie?",
  "description": "Jeśli jesteś programistą i chcesz programować przez osiem godzin w ramach pracy na etacie, to może to być niezwykle trudne do wykonania. Większość z nas już po kilku godzinach intensywnego kodowania czuje, że mózg zaczyna odmawiać posłuszeństwa. Autor artykułu sugeruje, że 3–4 godziny takiego głębokiego, skoncentrowanego programowania to maksimum, jakie człowiek jest w stanie osiągnąć. Podobno potwierdzają to badania psychologiczne. W artykule znajdziesz również kilka porad, które według autora mogą zwiększyć produktywność nawet pięciokrotnie.",
  "tags": ["deep work", "developer productivity", "meetings", "flow", "interruptions"],
  "category": "Work & Career",
  "suggested_category": null
}
```
