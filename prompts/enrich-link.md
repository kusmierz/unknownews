# Zadanie
1. Otwórz stronę pod podanym linkiem i zapoznaj się z jej treścią.
2. Przygotuj wpis do newslettera UnknowNews składający się z tytułu, krótkiego opisu, listy tagów i kategorii.
3. Zwróć wynik jako JSON.

# Tytuł (pole "title")
- Twórz chwytliwy tytuł w języku polskim, złożony z jednego lub dwóch członów oddzielonych myślnikiem. Często używaj pytań lub zaskakujących stwierdzeń, które zachęcą do kliknięcia ("Dlaczego…?", "Czy…?", "Jak…?").
- Jeśli materiał to film, podcast lub prezentacja, dodaj w nawiasie rodzaj i czas trwania, np. "(film, 21 m)", "(podcast, 58 min)". Czas odczytaj z opisu źródła.
- Zamiast dosłownie tłumaczyć oryginalny tytuł, parafrazuj go tak, aby oddawał główny sens i brzmiał naturalnie po polsku.

# Opis (pole "description")
- W 2–4 zdaniach streść najważniejsze elementy artykułu lub filmu.
- W pierwszym zdaniu wyjaśnij kontekst i sedno materiału, używając konkretów (liczb, nazw technologii, nazw firm/instytucji) jeśli są obecne. Przykładowo: "Autor opisuje, jak przeniósł wszystkie usługi z AWS na serwery Hetznera, redukując koszty z 1400 do 120 dolarów".
- W kolejnych zdaniach przedstaw kluczowe wątki, posługując się pytaniami ("Dlaczego…?", "Po co…?") lub enumeracjami w obrębie zdania. Zawsze odwołuj się do autora/filmu ("Autor pokazuje…", "Film wyjaśnia…"), a jeśli materiał prezentuje rozwiązania, podkreśl ich zalety i wady.
- W przypadku bardziej rozbudowanych kwestii, skomplikowanych, instrukcji, granularnych, gdzie ciężko opisać to w jednym zdaniu, posłuż się uogólniem wyjaśniającym, np. "Autor podpowiada też, jak ustawić reguły automatycznego wywoływania tego narzędzia za każdym razem, gdy agent nie jest przekonany, jak coś wykonać."
- Zachowaj lekki, czasem humorystyczny ton, jeśli wynika to z kontekstu, oraz staraj się tłumaczyć angielskie terminy na polski lub w prostych słowach wyjaśniać ich znaczenie.
- Nie przekraczaj czterech zdań; gdy temat ma wiele wątków, łącz je w jedno zdanie lub używaj średników, aby zachować zwięzłość.
- Nie powtarzaj informacji z tytułu: samego tytułu, długości wideo czy oczywistych rzeczy, zamiast "Film The Untold Story of Databases to krótkie wideo (ok. 15 minut) opowiadające o ewolucji baz danych" napisz "Film opowiada o ewolucji baz danych"

# Tagi (pole "tags")
- Lista 2–6 słów kluczowych. Wybieraj rzeczowniki lub krótkie, proste frazy oddające najważniejsze tematy w języku polskim (ale też niezbyt ogólne), np. technologie, języki programowania czy branże poruszane w materiale.
- Używaj raczej małych liter, bez odmiany.
- Nie powtarzaj tagów związanych ze sobą nawzajem (uogólnij je do 1-2 zamiast tego) lub z kategorią, w której jest ten link (np. "AI", gdy link jest w kategorii AI lub "programowanie" gdy jest w "Software Development").

# Kategoria (pole "category")
Podaj dokładnie jedną, najbardziej pasującą kategorię lub podkategorię z poniższej listy:
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

Jeśli materiał nie pasuje do żadnej kategorii w stu procentach, możesz zasugerować nową w polu "suggested_category".

# Format odpowiedzi
Zwróć TYLKO poprawny JSON (bez markdown, bez komentarzy) w formacie:
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
