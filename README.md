Om een script te runnen MOET je je script in dezelfde directory zetten als je prompt.txt bestand. Daarnaast MOET je een werkende google key hebben in de vorm van een service_account.json file die je ook in diezelfde directory moet hebben tenzij je een ander model wilt gebruiken. In dat geval voel je vrij om dit script over te nemen en aan te passen.

De prompts zullen in Github verschillende namen hebben. Als je de testen wilt uitvoeren met het script zal je je txt telkens moeten hernoemen naar "prompt.txt". Als je dit niet doet kan het script niet de prompt uitlezen.

Voor testen met referentie materiaal moet je bij elke test de images renamen naar "reference1.jpg", "reference2.jpg", "reference3.jpg" en zo voort.

Voor de laatste test, om afbeeldingen te genereren, moet je een .env file opstellen. In de .env file moet je 3 verschillende variablen opstellen: GENAI_API_KEY, GENAI_BASE_URL, GENAI_IMAGE_MODEL.