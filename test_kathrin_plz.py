"""
Test mit echtem Transkript wo PLZ 14793 fehlt.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

import json
from resume_builder import ResumeBuilder

print("=" * 70)
print("TEST: ECHTES TRANSKRIPT - PLZ FEHLT")
print("=" * 70)

# Real transcript from user - PLZ is 14793
test_transcript = [
    {"speaker": "A", "text": "Hallo."},
    {"speaker": "B", "text": "Guten Tag Kathrin, hier ist die Bewerbungs-Assistenz von Klinik Ernst von Bergmann Bad Belzig gGmbH. Sie hatten sich bei uns beworben. Haben Sie denn gerade Zeit?"},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "Bevor wir starten, bräuchte ich noch kurz Ihre Zustimmung: Dürfen wir Ihre Angaben für Bewerbungszwecke speichern und an unser Recruiting-Team weitergeben?"},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "Vielen Dank. Dann würde ich jetzt gern ein bisschen besser verstehen, was Sie zu der Bewerbung bewegt hat. Vielleicht können Sie mir ein wenig erzählen, wie es dazu gekommen ist, dass Sie sich bei uns vorstellen möchten?"},
    {"speaker": "A", "text": "Ja, ich bin auf der Suche nach einer neuen Herausforderung und habe dann Ihre Stelle gesehen, dass Sie neue Mitarbeiter suchen in der Pflege. Und ich bin gelernte Altenpflegerin."},
    {"speaker": "B", "text": "Danke für die Einblicke. Eine neue Herausforderung klingt spannend. Damit ich Ihren fachlichen Hintergrund einordnen kann: Sie haben also eine Ausbildung als Altenpflegerin abgeschlossen. Wie lange arbeiten Sie schon in diesem Bereich?"},
    {"speaker": "A", "text": "Seit über zehn Jahren."},
    {"speaker": "B", "text": "Das ist eine beachtliche Erfahrung. Kurz zur Einordnung bezüglich der Sprachkenntnisse: Wie würden Sie Ihre Deutschkenntnisse selbst einschätzen?"},
    {"speaker": "A", "text": "Meine Muttersprache."},
    {"speaker": "B", "text": "Sehr gut, vielen Dank. Was ist Ihnen bei der Wahl des Standorts wichtig? Unser Standort ist in Bad Belzig. Passt das für Sie?"},
    {"speaker": "A", "text": "Ja, das ist in der Nähe zu meinem Wohnort. Ich bin nämlich vor kurzem nach Cäsar gezogen und daher passt das."},
    {"speaker": "B", "text": "Das ist praktisch, wenn der Arbeitsweg nicht zu lang ist. Wenn Sie an Ihren nächsten Arbeitgeber denken - was ist Ihnen dort besonders wichtig?"},
    {"speaker": "A", "text": "Ja, was ist mir besonders wichtig? Die Nähe zu meinem Wohnort, Weiterbildungsmöglichkeiten, so."},
    {"speaker": "B", "text": "Danke für diese Einblicke. Weiterbildungsmöglichkeiten und ein kurzer Arbeitsweg sind definitiv wichtige Faktoren. Bevor wir weitergehen, möchte ich Ihnen kurz unser Unternehmen vorstellen: Wir sind ein innovatives Gesundheitsunternehmen in Bad Belzig, das Fachkräfte in den Bereichen Beatmungsmedizin und plastische Chirurgie sucht. Bei uns erwarten Sie flexible Arbeitszeitmodelle und ein wertschätzendes Arbeitsumfeld. Wie klingt das für Sie?"},
    {"speaker": "B", "text": "Könnten Sie sich grundsätzlich vorstellen, in so einem Umfeld zu arbeiten?"},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "Gut, danke für Ihre Rückmeldung..."},
    {"speaker": "A", "text": "Das klingt gut!"},
    {"speaker": "B", "text": "Das freut mich zu hören! Dann würde ich jetzt gern ein bisschen genauer darauf eingehen, was für Sie persönlich im Arbeitsalltag gut passen würde. Ich möchte kurz auf das Arbeitszeitmodell eingehen: Haben Sie eine Präferenz bezüglich Vollzeit oder Teilzeit – oder sind Sie da flexibel?"},
    {"speaker": "A", "text": "Ich würde gerne Vollzeit arbeiten."},
    {"speaker": "B", "text": "Sehr gut. Welcher Bereich kommt für Sie in Frage – interessiert Sie eher die Beatmungsmedizin oder die plastische Chirurgie?"},
    {"speaker": "A", "text": "Die plastische Chirurgie!"},
    {"speaker": "B", "text": "Ausgezeichnet. Dann würde ich gern noch ein paar Details zu Ihrer Ausbildung und Ihrem beruflichen Werdegang erfassen, damit wir ein vollständiges Bild haben. Sie haben erwähnt, dass Sie gelernte Altenpflegerin sind – das ist Ihre formale Ausbildung, richtig? Wo haben Sie diese Ausbildung absolviert?"},
    {"speaker": "A", "text": "Ja"},
    {"speaker": "B", "text": "Können Sie mir..."},
    {"speaker": "A", "text": "eine dreijährige Ausbildung"},
    {"speaker": "B", "text": "Verstanden, eine dreijährige Ausbildung zur Altenpflegerin. In welchem Jahr haben Sie diese abgeschlossen?"},
    {"speaker": "A", "text": "Ich habe eine 2013 abgeschlossen."},
    {"speaker": "B", "text": "Danke. Und wo haben Sie diese Ausbildung gemacht – an welcher Institution oder in welchem Bundesland?"},
    {"speaker": "A", "text": "In der Ecolea in Stralsund und das ist in Mecklenburg-Vorpommern."},
    {"speaker": "B", "text": "Gut, danke. Das war also in Deutschland. Dann hätte ich gern noch einen kurzen Überblick über Ihre beruflichen Stationen: Wo haben Sie nach Ihrer Ausbildung gearbeitet – können Sie mir die letzten zwei, drei Arbeitgeber kurz nennen?"},
    {"speaker": "A", "text": "Der letzte Arbeitgeber war die Diakonie in Rostock im Ambulantendienst. Davor habe ich im DRK in einem Pflegeheim gearbeitet und davor war die Volkssolidarität, das war auch ein ambulanter Pflegedienst."},
    {"speaker": "B", "text": "Danke für den Überblick. Damit ich das richtig einordne: Bei der Diakonie in Rostock – wie lange haben Sie dort im Ambulantendienst gearbeitet?"},
    {"speaker": "A", "text": "Etwa ein Jahr."},
    {"speaker": "B", "text": "Alles klar. Und beim DRK im Pflegeheim – wie lange war das ungefähr?"},
    {"speaker": "A", "text": "Vier Jahre."},
    {"speaker": "B", "text": "Verstanden. Und bei der Volkssolidarität im ambulanten Pflegedienst – wie lange waren Sie dort tätig?"},
    {"speaker": "A", "text": "Zwei Jahre."},
    {"speaker": "B", "text": "Danke, das hilft mir sehr. Bevor wir zum Abschluss kommen, brauche ich noch ein paar organisatorische Angaben. Zunächst: Wann könnten Sie denn bei uns starten – haben Sie da einen zeitlichen Rahmen im Kopf?"},
    {"speaker": "A", "text": "Zum 1. März könnte ich starten. 1.3.,"},
    {"speaker": "B", "text": "Perfekt, zum 1. März – das ist notiert. Jetzt brauche ich noch Ihre Postleitzahl, damit wir Sie richtig zuordnen können. Wie lautet Ihre Postleitzahl?"},
    {"speaker": "A", "text": "14793"},
    {"speaker": "B", "text": "Danke. Das ist sieben eins vier sieben neun drei – habe ich das richtig?"},
    {"speaker": "A", "text": "..."},
    {"speaker": "B", "text": "Entschuldigung, können Sie mir die Postleitzahl nochmal wiederholen? Ich möchte sichergehen, dass ich sie richtig notiert habe."},
    {"speaker": "A", "text": "Das ist die 14793"},
    {"speaker": "B", "text": "Danke. Also eins vier sieben neun drei – stimmt das so?"},
    {"speaker": "A", "text": "Ja stimmt!"},
    {"speaker": "B", "text": "Perfekt, danke. Haben Sie denn noch eine Frage an mich oder gibt es noch etwas, das Sie gerne wissen möchten?"},
    {"speaker": "A", "text": "Im Moment nicht, nein."},
    {"speaker": "B", "text": "Gut. Dann fasse ich kurz zusammen, was wir besprochen haben: Sie sind gelernte Altenpflegerin mit über zehn Jahren Berufserfahrung, haben Ihre Ausbildung 2013 in Stralsund abgeschlossen und möchten gerne Vollzeit in der plastischen Chirurgie bei uns arbeiten. Sie können zum 1. März starten und wohnen in der Nähe von Bad Belzig. Das passt sehr gut zu unseren Anforderungen."},
    {"speaker": "A", "text": "Ja"},
    {"speaker": "B", "text": "Unser Recruiting-Team wird sich in den nächsten Tagen bei Ihnen melden und die nächsten Schritte mit Ihnen besprechen. Sie werden über den Rückruf informiert. Vielen Dank, dass Sie sich die Zeit für das Gespräch genommen haben, Kathrin. Ich wünsche Ihnen alles Gute und freue mich, dass wir Sie kennengelernt haben. Auf Wiederhören!"}
]

print(f"\nTranskript: {len(test_transcript)} Zeilen")
print(f"PLZ wird erwähnt in Zeile 40: '14793'")
print(f"PLZ wird wiederholt in Zeile 44: 'Das ist die 14793'")

print("\n" + "=" * 70)
print("VERARBEITUNG...")
print("=" * 70)

builder = ResumeBuilder(prefer_claude=True)

try:
    result = builder.build_resume(
        transcript=test_transcript,
        elevenlabs_metadata={"conversation_id": "kathrin_test", "candidate_first_name": "Kathrin"},
        temporal_context={"call_date": "2026-01-16", "call_year": 2026}
    )
    
    print("\n" + "=" * 70)
    print("ERGEBNIS:")
    print("=" * 70)
    
    plz_applicant = result.applicant.postal_code
    plz_resume = result.resume.postal_code
    city = result.resume.city
    
    print(f"\n1. PLZ im Applicant: {plz_applicant}")
    print(f"2. PLZ im Resume: {plz_resume}")
    print(f"3. Stadt: {city}")
    
    print("\n" + "=" * 70)
    
    if plz_applicant == "14793" and plz_resume == "14793":
        print("SUCCESS! PLZ korrekt extrahiert aus langem Gespraech!")
        print("Die PLZ-Extraktion funktioniert!")
    elif plz_applicant or plz_resume:
        print(f"TEILWEISE: PLZ extrahiert aber falsch!")
        print(f"Erwartet: 14793")
        print(f"Erhalten: {plz_applicant or plz_resume}")
    else:
        print("FEHLER: PLZ NICHT extrahiert!")
        print("Das ist das Problem - LLM findet PLZ nicht!")
    
    print("=" * 70)
    
    # Show experiences
    print(f"\nExperiences: {len(result.resume.experiences)}")
    for i, exp in enumerate(result.resume.experiences, 1):
        print(f"  {i}. {exp.position} bei {exp.company}")
    
    # Show educations
    print(f"\nEducations: {len(result.resume.educations)}")
    for i, edu in enumerate(result.resume.educations, 1):
        print(f"  {i}. {edu.description} - {edu.company}")
    
    # Save result
    output_path = "Output/test_kathrin_plz.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result.model_dump(), f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\nErgebnis gespeichert: {output_path}")
    
except Exception as e:
    print(f"\nFEHLER: {e}")
    import traceback
    traceback.print_exc()
