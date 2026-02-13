"""Local test script for CallAnalyzer - run with: python test_analysis_local.py"""
import os
import sys
import json
import logging

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env
from dotenv import load_dotenv
load_dotenv()

# Verify API keys
if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
    print("ERROR: Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY found in .env")
    sys.exit(1)

print(f"[CONFIG] ANTHROPIC_API_KEY: {'set' if os.getenv('ANTHROPIC_API_KEY') else 'not set'}")
print(f"[CONFIG] OPENAI_API_KEY: {'set' if os.getenv('OPENAI_API_KEY') else 'not set'}")

# Test transcript (from user)
TRANSCRIPT = [
    {"speaker": "A", "text": "Hallo, guten Morgen. Hallo."},
    {"speaker": "B", "text": "Guten Tag Davids, hier ist die Bewerbungs-Assistenz von Korian Zentrale. Sie hatten sich bei uns beworben. Haben Sie..."},
    {"speaker": "A", "text": "Guten Tag. Ja, ich habe das gerade gemacht. Guten Morgen."},
    {"speaker": "B", "text": "Guten..."},
    {"speaker": "A", "text": "Hallo? Ja?"},
    {"speaker": "B", "text": "Guten..."},
    {"speaker": "A", "text": "ich habe gerade das... Ich habe das gerade gemacht"},
    {"speaker": "B", "text": "Ja, verstanden. Haben Sie gerade Zeit für das Gespräch? Es dauert ungefähr 15 Minuten."},
    {"speaker": "A", "text": "Ja, können. Ich will ja."},
    {"speaker": "B", "text": "Gut..."},
    {"speaker": "A", "text": "Ja, können das machen."},
    {"speaker": "B", "text": "Schön. Bevor wir starten, bräuchte ich kurz Ihre Zustimmung: Dürfen wir Ihre Angaben für Bewerbungszwecke speichern und an unser Recruiting-Team weitergeben?"},
    {"speaker": "A", "text": "Ja, kann man das machen."},
    {"speaker": "B", "text": "Gut, danke. Dann würde ich jetzt gern besser verstehen, was Sie zu der Bewerbung bewegt hat. Erzählen Sie mir gern – wie ist es dazu gekommen?"},
    {"speaker": "A", "text": "Noch mal?"},
    {"speaker": "B", "text": "Ja, gerne. Was hat..."},
    {"speaker": "A", "text": "Hallo?"},
    {"speaker": "B", "text": "Ja, ich bin noch da. Was hat Sie dazu bewogen, sich bei uns zu bewerben?"},
    {"speaker": "A", "text": "Ich habe ihn bewerben, als Pflegefachmann. Ein Einstiegelehrer als Pflegefachmann."},
    {"speaker": "B", "text": "Verstehe. Sie haben sich also als Pflegefachmann beworben. Was war für Sie der..."},
    {"speaker": "A", "text": "Ja, Pflegefachmann bewirken, ja."},
    {"speaker": "B", "text": "Alles klar. Was war für Sie der wichtigste Grund, sich bei Korian Zentrale zu melden?"},
    {"speaker": "A", "text": "Ja, ich habe eine Information über Korean Deutschland gehört. Die gefällt mir nicht, deswegen habe ich mich beworben."},
    {"speaker": "B", "text": "Danke für die Einblicke. Sie haben also von Korian gehört und das hat Sie interessiert. Was ist Ihnen bei einem Arbeitgeber besonders wichtig?"},
    {"speaker": "A", "text": "Was kann ich sagen? Die Arbeitgeber wissen, was gut ist für die Mitarbeiter. Also für mich habe ich keine speziellen Wünsche. Die Regeln, die arbeiten in Korea, sind okay, dann kann man arbeiten. Ich habe keine speziellen Wünsche, nein, habe ich nicht."},
    {"speaker": "B", "text": "Das kann ich gut nachvollziehen. Dann noch eine wichtige Frage zu den Sprachkenntnissen: Ist Deutsch Ihre Muttersprache?"},
    {"speaker": "A", "text": "Deutsch ist nicht meine Muttersprache aber ich habe Deutsch gelernt und ich habe die B1 und B1 bis zum 2. Februar 2017."},
    {"speaker": "B", "text": "Alles klar, danke. Sie haben also B1-Kenntnisse. Das ist notiert. Dann erzähle ich Ihnen kurz etwas über Korian..."},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "Wir sind ein innovativer Pflegeanbieter, der engagierte Fachkräfte sucht, um unser Team zu verstärken. Bei uns erwarten Sie nicht nur ein wertschätzendes Arbeitsumfeld, sondern auch Unterstützung bei der Karriereentwicklung und individuelle Hilfestellung, wie zum Beispiel bei der Erstellung Ihres Lebenslaufs. Das ist uns wichtig.\n\nJetzt hätte ich noch ein paar Fragen zu Ihren..."},
    {"speaker": "A", "text": "Das wundert mich."},
    {"speaker": "B", "text": "Was wundert Sie..."},
    {"speaker": "A", "text": "Das ist wunderbar."},
    {"speaker": "B", "text": "Ja, das..."},
    {"speaker": "A", "text": "Ja? Die, die, die, die, die, Light...die Telefon ist nicht so gut."},
    {"speaker": "B", "text": "Ah,..."},
    {"speaker": "A", "text": "Hallo?"},
    {"speaker": "B", "text": "Ja, ich bin noch da. Die Verbindung ist vielleicht etwas schwach – kein Problem. Dann..."},
    {"speaker": "A", "text": "Ja, die Verbindung ist etwas schwacher. Muss man da sagen."},
    {"speaker": "B", "text": "Verstanden. Dann machen wir weiter. Ich hätte noch ein paar Fragen zu Ihren Vorstellungen. Dürfen wir Sie auch für andere passende Stellen kontaktieren?"},
    {"speaker": "A", "text": "Ok. Wir?"},
    {"speaker": "B", "text": "Ja, unser..."},
    {"speaker": "A", "text": "Hallo?!"},
    {"speaker": "B", "text": "Ja, ich bin noch da. Mit \"wir\" meine ich unser..."},
    {"speaker": "A", "text": "Hallo?! Oh ja!"},
    {"speaker": "B", "text": "Ja, ich bin hier. Mit \"wir\" meine ich unser Recruiting-Team von Korian. Dürfen wir Sie auch für andere passende Stellen kontaktieren, falls etwas Passendes dabei ist?"},
    {"speaker": "A", "text": "Oh, ich möchte gerne in Corian arbeiten wenn es die Möglichkeit gibt, muss man so sagen. Deswegen habe ich nicht direkt mit ihr"},
    {"speaker": "B", "text": "Gut, verstanden. Das ist eine klare Antwort. Ist es in Ordnung, wenn wir Ihnen beim Erstellen des Lebenslaufs helfen?"},
    {"speaker": "A", "text": "Bitte? Die Verbindung ist ganz, ganz, ganz weit... Hallo?!"},
    {"speaker": "B", "text": "Hallo, können Sie mich..."},
    {"speaker": "A", "text": "Hallo?! Ja jetzt! Vorne her. Die letzte Frage habe ich nicht beantwortet. Ich habe sie nicht gehört."},
    {"speaker": "B", "text": "Ah, verstanden. Ich wiederhole die Frage: Ist es in Ordnung, wenn wir Ihnen beim Erstellen des Lebenslaufs helfen?"},
    {"speaker": "A", "text": "Ja ich kann meinen Lebenslauf erstellen wenn Sie das wollen."},
    {"speaker": "B", "text": "Gut, danke. Und noch eine letzte Frage zu den Vorstellungen: Möchten Sie per SMS über den Stand Ihrer Bewerbung informiert werden?"},
    {"speaker": "A", "text": "Das wäre eine E-Mail, ich habe Ihnen eine E-Mail auch geschenkt."},
    {"speaker": "B", "text": "Alles klar, verstanden. Sie bevorzugen E-Mail. Das notiere ich. Dann würde ich jetzt gern auf Ihre Ausbildung und Qualifikation eingehen. Welchen Schulabschluss haben Sie?"},
    {"speaker": "A", "text": "Schulabschluss? Ich habe in der Pflegefachmannschaft also ja etwas Pflegefachmann"},
    {"speaker": "B", "text": "..."},
    {"speaker": "A", "text": ". Der in der Kölner College."},
    {"speaker": "B", "text": "Alles klar. Sie haben also eine Ausbildung zum Pflegefachmann gemacht. An welcher Institution war das – können Sie mir den Namen der Schule oder des Colleges..."},
    {"speaker": "A", "text": "Ja"},
    {"speaker": "B", "text": "Ja, können Sie mir..."},
    {"speaker": "A", "text": ", der Kölner College. Da ist es in Elsa."},
    {"speaker": "B", "text": "Okay, notiert – Kölner..."},
    {"speaker": "A", "text": "Ufenmutter, der Kölner College, Ufenmutter."},
    {"speaker": "B", "text": "Alles klar. Das ist in Köln. Wann haben Sie diese Ausbildung zum Pflegefachmann abgeschlossen – welcher Monat und welches Jahr?"},
    {"speaker": "A", "text": "Ja, ich habe die Hausbeziehung im Juni fertig gemacht, aber ich habe nicht einen Teil des Schriftlich bestellt. Deswegen habe ich noch zwei oder drei Monate das wiederholt, bis zum General, der zweite oder dritte. Dann habe ich das bestellt, deswegen. Ich habe meine Zertifikate nicht mehr geworfen, bis zum General. Aber ich habe die Schule fertig seit Juni. Habe nicht die einen Stiftungsteile nicht bestanden, so ich hab das wiederholt."},
    {"speaker": "B", "text": "Verstehe. Also die Ausbildung war im Juni fertig, aber Sie..."},
    {"speaker": "A", "text": "Hallo?"},
    {"speaker": "B", "text": "Ja, ich bin noch..."},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "Sie haben also die Ausbildung im Juni abgeschlossen, aber mussten noch einen Teil wiederholen. In welchem Jahr war das – Juni welches Jahr?"},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "Welches Jahr war das?"},
    {"speaker": "A", "text": "Ich habe in der Sammelschrift geschrieben, November. Ja, November."},
    {"speaker": "B", "text": "Alles klar. Also November – welches Jahr war das?"},
    {"speaker": "A", "text": "Das ist 2025."},
    {"speaker": "B", "text": "Gut, notiert – November 2025. Dann haben Sie die Ausbildung zum Pflegefachmann also im November..."},
    {"speaker": "A", "text": "Ja"},
    {"speaker": "B", "text": "..."},
    {"speaker": "A", "text": ". Aber ich bekomme die Urkunde seit 1. Januar, das heißt seit 21 Dezember habe ich die Ergebnis bekommen, dann erst 1. und 2. Januar bekommst du die Urkunde"},
    {"speaker": "B", "text": "Alles klar, verstanden. Sie haben die Ergebnisse im..."},
    {"speaker": "A", "text": ". Verstehst du meine?"},
    {"speaker": "B", "text": "Ja, ich verstehe. Sie haben die Ergebnisse bekommen und die Urkunde kommt Anfang Januar. Das ist notiert. Jetzt noch eine Frage: Haben Sie vor dieser Ausbildung einen..."},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "...Schulabschluss gemacht – zum Beispiel Hauptschule, Realschule oder Abitur?"},
    {"speaker": "A", "text": "Ach so, ich habe in der deutschen Sprache die Hauptschule Abschluss gemacht. Danach habe ich den Pflegeassistentenkurs für zwei Jahre kursesoviert. Danach kommt es ins Pflegefachmannskurs. So, ich habe den Hauptschulabschluss, Pflegeassistenten kursesoviert sowie Pflegefachmann"},
    {"speaker": "B", "text": "Danke für die Erklärung. Also Sie haben Hauptschulabschluss, dann Pflegeassistent und jetzt Pflegefachmann. Das ist notiert. War die Ausbildung in Deutschland oder im..."},
    {"speaker": "A", "text": "Ja"},
    {"speaker": "B", "text": "...Ausland?"},
    {"speaker": "A", "text": "Ja, alles ist in Deutschland. Von A1 bis Pflegepharma in Rufenbüttel."},
    {"speaker": "B", "text": "Alles klar, alles in Deutschland – in Rufenbüttel. Danke. Jetzt würde ich gern auf Ihren beruflichen Werdegang..."},
    {"speaker": "A", "text": "Bitte?"},
    {"speaker": "B", "text": "Ich würde gern auf Ihren beruflichen Werdegang eingehen. Wo haben Sie denn zuletzt gearbeitet – vor oder neben der Ausbildung?"},
    {"speaker": "A", "text": "Also Pflegeheimen kamen bei meinen Ausbildungsjäger an der Org. Ich habe in den Praxis, auch in Abo und anderen Pflegeheimen gearbeitet. Während der Praxis war ich in den Pflegeassistenten und wie die Pflegefachmann. Bei dem Pflegefachmann habe ich Abo gearbeitet. Und im Pflegeassistenten haben andere auch ein paar andere Pflegeheime gearbeitet."},
    {"speaker": "B", "text": "Verstehe. Sie haben also während der Ausbildung in verschiedenen Pflegeheimen praktiziert. Können Sie mir die letzte oder aktuelle Arbeitsstelle nennen – Arbeitgeber, Standort und wann Sie dort angefangen haben?"},
    {"speaker": "A", "text": "Oh, kann ich nicht erzählen. Okay, ich würde sagen 20-24 habe ich angefangen, die Pflegefragmannsbildung und da war bei mir Träger Abo, Pflegeheim. Abo wohnt im Pflegeheim in Kamp, ja. Dann 2022."},
    {"speaker": "B", "text": "Alles klar. Also Sie haben 2020 angefangen mit der Ausbildung bei Abo Pflegeheim in Kamp. Und wann endet oder endete diese Stelle – oder..."},
    {"speaker": "A", "text": "So."},
    {"speaker": "B", "text": "...arbeiten..."},
    {"speaker": "A", "text": "202.000 2200. Aber nicht fliege, aber nicht, aber fliege und wohnen fliege heim in Kamp gearbeitet."},
    {"speaker": "B", "text": "Okay, verstanden. Sie haben also bei Abo Pflegeheim in Kamp gearbeitet. Wann haben Sie dort angefangen und wann endete die Stelle – oder..."},
    {"speaker": "A", "text": "Ja"},
    {"speaker": "B", "text": "arbeiten Sie noch dort?"},
    {"speaker": "A", "text": ". Nein ich arbeite nicht mehr da nach der Ausbildung habe ich den Platz verlassen."},
    {"speaker": "B", "text": "Alles klar. Wann haben Sie die Stelle verlassen – welcher Monat und Jahr?"},
    {"speaker": "A", "text": "Der letzte Monat. Wir sind ja im Februar aber im Januar. Januar 30 am 16 habe ich das verlaessen am Ende Januar"},
    {"speaker": "B", "text": "Gut, notiert – Ende Januar 2026. Und davor – haben Sie noch eine andere Arbeitsstelle, bevor Sie die..."},
    {"speaker": "A", "text": "Ja."},
    {"speaker": "B", "text": "Ausbildung angefangen haben?"},
    {"speaker": "A", "text": "Nein. Ja, das war der Pflegeassistentenkurs. Da bin ich in zwei anderen Pflegeheimen gearbeitet. Erstmal war ich in Kuranium, wo die Mutter gerufen hat. Dann war es ein ambulanter Pflegedienst, da habe ich auch gearbeitet. Aufs Praxis, aufs Praxis-Instanz."},
    {"speaker": "B", "text": "Verstehe. Also während des Pflegeassistentenkurses haben Sie in zwei Pflegeheimen gearbeitet – Kuranium und einem ambulanten Pflegedienst. Können Sie mir noch die Zeiträume sagen – wann..."},
    {"speaker": "A", "text": "Ja. Ja."},
    {"speaker": "B", "text": "haben Sie dort angefangen und wann endete das?"},
    {"speaker": "A", "text": "Wow, das kann man schon 20... Ja, ja. Ja, das ist..."},
    {"speaker": "B", "text": "Nehmen Sie sich gern Zeit."},
    {"speaker": "A", "text": "Ja. Schwank sie schwankt sich dies. Schwankt sich, schwankt sich, schwankt sich ja."},
    {"speaker": "B", "text": "Kein Problem. Wir haben Zeit. Können Sie mir grob sagen – war das 2018, 2019, 2020?"},
    {"speaker": "A", "text": "Dann ist 2018 war 2020 bis 2023. Da war die Assistentin. Da war die Zeitraum für die Assistenten Kurs der 2000 20. 2000 2022 bis 2025, aber nicht die Pflege, Pflegefachmann und dann fertig gemacht."},
    {"speaker": "B", "text": "Alles klar. Also der Pflegeassistentenkurs war von 2020 bis 2022, und dann die Pflegefachmann-Ausbildung von 2022 bis November 2025. Das ist notiert. Jetzt noch eine wichtige Frage: Können Sie mir Ihre..."},
    {"speaker": "A", "text": "Genau."},
    {"speaker": "B", "text": "Postleitzahl nennen?"},
    {"speaker": "A", "text": "3a300. Wofür wurde das? 3a300, wofür wurde das?"},
    {"speaker": "B", "text": "Das ist für unsere Unterlagen – damit wir wissen, wo Sie wohnen. Sie sagten 3a300?"},
    {"speaker": "A", "text": "Ja, 3a300. Wofür wurde das? Wollen Sie die Haftnummer auch?"},
    {"speaker": "B", "text": "Nein, die Postleitzahl reicht. Aber ich möchte sichergehen – ist das 3, a, 3, 0, 0?"},
    {"speaker": "A", "text": "3a300"},
    {"speaker": "B", "text": "Alles klar. Und noch eine Frage: Welche Staatsangehörigkeit haben Sie?"},
    {"speaker": "A", "text": "Ja, das ist ein bisschen Problem, weil ich bin Libyrian. Ich bin Libyrian"},
    {"speaker": "B", "text": "Alles klar, verstanden. Sie sind libyscher Staatsangehörigkeit. Das ist notiert. Gibt es noch etwas, das Sie mir..."},
    {"speaker": "A", "text": "Ja!"},
    {"speaker": "B", "text": "gern mitteilen möchten – etwas, das wir noch nicht besprochen haben?"},
    {"speaker": "A", "text": "Das gibt es nicht. Das gibt es nicht. Das gibt es nicht. Das gibt es nicht momentan."},
    {"speaker": "B", "text": "Gut. Dann hätte ich noch eine kurze Frage zur Erreichbarkeit: Unter welcher Telefonnummer können wir Sie am besten erreichen?"},
    {"speaker": "A", "text": "0176 84660345"},
    {"speaker": "B", "text": "Alles klar, notiert – 0176 84660345. Und die E-Mail-Adresse, unter der Sie sich beworben haben – können Sie mir die noch mal bestätigen?"},
    {"speaker": "A", "text": "davisbenjamin587 at gmail.com"},
    {"speaker": "B", "text": "Perfekt, notiert – davisbenjamin587 at gmail.com. Dann fasse ich kurz zusammen, was wir besprochen haben: Sie haben sich als Pflegefachmann bei Korian beworben. Sie haben Hauptschulabschluss, dann Pflegeassistent und jetzt Pflegefachmann – alles in Deutschland, in Rufenbüttel. Ihre letzte Stelle war bei Abo Pflegeheim in Kamp, die Sie Ende Januar verlassen haben. Ihre Postleitzahl ist 33300, Sie sind libyscher Staatsangehörigkeit und Ihre E-Mail ist..."},
    {"speaker": "A", "text": "Schuldigung? Nein, nein. Drei acht. Drei acht, drei null null."},
    {"speaker": "B", "text": "..."},
    {"speaker": "A", "text": "Drei acht, drei null null."},
    {"speaker": "B", "text": "Ah, danke für den Hinweis. Ich korrigiere das – die Postleitzahl ist 3, 8, 3, 0, 0 – also 38300. Richtig?"},
    {"speaker": "A", "text": "Genau."},
    {"speaker": "B", "text": "Gut, danke. Dann sind wir fast fertig. Die nächsten Schritte sind: Unser Recruiting-Team wird sich in den nächsten Tagen bei Ihnen melden – entweder per E-Mail oder Telefon unter der Nummer, die Sie mir gegeben haben. Sie erhalten dann weitere Informationen zum Bewerbungsprozess. Haben Sie noch Fragen für mich?"},
    {"speaker": "A", "text": "Momentan nein. Aber ich habe nicht was zu sagen. Ich wollte nicht Löwe sagen, aber ich freue mich, dass sie gut Englisch hat. Das freut mich sehr"},
    {"speaker": "B", "text": "Das freut mich zu hören. Vielen Dank für das Gespräch und für Ihre Offenheit. Alles Gute für Sie – und wir melden uns bald bei Ihnen. Auf Wiedersehen!"},
]

# Metadata (simulated - this call completed normally, not a hangup)
METADATA = {
    "conversation_id": "test_local_001",
    "call_duration_secs": 720,  # ~12 minutes (long call)
    "termination_reason": "end_call tool was called.",
    "call_successful": "success",
    "company_name": "Korian Zentrale",
    "campaign_role_title": "Pflegefachmann",
    "campaign_id": "test_campaign",
}


def main():
    print("\n" + "=" * 80)
    print("  CALL ANALYZER - LOCAL TEST")
    print("=" * 80 + "\n")
    
    print(f"Transcript turns: {len(TRANSCRIPT)}")
    print(f"Call duration: {METADATA['call_duration_secs'] / 60:.1f} min")
    print(f"Termination: {METADATA['termination_reason']}")
    print()
    
    # Import and run analyzer
    from call_analyzer import CallAnalyzer
    
    analyzer = CallAnalyzer()
    
    # Test as "long_call" (since >8 min)
    print("[TEST] Running analysis with trigger='long_call' ...")
    print("-" * 60)
    
    result = analyzer.analyze(
        transcript=TRANSCRIPT,
        metadata=METADATA,
        trigger="long_call"
    )
    
    if result is None:
        print("\n❌ Analysis returned None!")
        return
    
    print("\n" + "=" * 80)
    print("  ANALYSIS RESULTS")
    print("=" * 80)
    
    # Print key metrics
    print(f"\n[SCORE] Quality Score:      {result.get('quality_score')}/10")
    print(f"[SCORE] Engagement Score:   {result.get('engagement_score')}/10")
    print(f"[SCORE] Completeness Score: {result.get('completeness_score')}/10")
    print(f"[SCORE] Sentiment Trend:    {result.get('sentiment_trend')}")
    print(f"[SCORE] Avg Response:       {result.get('avg_response_length')}")
    print(f"[SCORE] Error Count:        {result.get('error_count')}")
    print(f"[SCORE] Rule Violations:    {result.get('rule_violation_count')}")
    print(f"[SCORE] Top Error:          {result.get('top_error_category')}")
    
    # Phases
    print(f"\n[PHASE] Last Completed Phase: {result.get('last_completed_phase')}")
    
    phases_completed = result.get('phases_completed', '[]')
    if isinstance(phases_completed, str):
        try:
            phases_completed = json.loads(phases_completed)
        except:
            pass
    print(f"[PHASE] Phases Completed: {phases_completed}")
    
    phases_missing = result.get('phases_missing', '[]')
    if isinstance(phases_missing, str):
        try:
            phases_missing = json.loads(phases_missing)
        except:
            pass
    print(f"[PHASE] Phases Missing: {phases_missing}")
    
    # Agent errors
    print(f"\n[ERROR] Agent Errors ({result.get('error_count', 0)}):")
    agent_errors = result.get('agent_errors', '[]')
    if isinstance(agent_errors, str):
        try:
            agent_errors = json.loads(agent_errors)
        except:
            agent_errors = []
    for err in agent_errors:
        print(f"   - [{err.get('category')}] (severity {err.get('severity')}/10, phase {err.get('phase')})")
        print(f"     {err.get('description')}")
    
    # Rule violations
    print(f"\n[RULE] Rule Violations ({result.get('rule_violation_count', 0)}):")
    violations = result.get('rule_violations', '[]')
    if isinstance(violations, str):
        try:
            violations = json.loads(violations)
        except:
            violations = []
    for v in violations:
        print(f"   - [{v.get('rule')}] (severity {v.get('severity')}/10, phase {v.get('phase')})")
        print(f"     {v.get('description')}")
    
    # Signs
    confusion = result.get('signs_of_confusion', '[]')
    if isinstance(confusion, str):
        try:
            confusion = json.loads(confusion)
        except:
            confusion = []
    if confusion:
        print(f"\n[CONFUSION] Signs of Confusion:")
        for s in confusion:
            print(f"   - {s}")
    
    # Summary
    print(f"\n[SUMMARY]:")
    print(f"   {result.get('analysis_summary')}")
    
    # Improvements
    improvements = result.get('improvement_suggestions', '[]')
    if isinstance(improvements, str):
        try:
            improvements = json.loads(improvements)
        except:
            improvements = []
    if improvements:
        print(f"\n[IMPROVE] Improvement Suggestions:")
        for i, s in enumerate(improvements, 1):
            print(f"   {i}. {s}")
    
    # Save full result
    output_path = os.path.join(os.path.dirname(__file__), "..", "Output", "test_analysis_result.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Convert all values to serializable format
    serializable_result = {}
    for k, v in result.items():
        if isinstance(v, str):
            try:
                serializable_result[k] = json.loads(v)
            except:
                serializable_result[k] = v
        else:
            serializable_result[k] = v
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(serializable_result, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Full result saved to: {output_path}")
    print()


if __name__ == "__main__":
    main()
