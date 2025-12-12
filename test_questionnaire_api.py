"""Test script for questionnaire API integration."""
import os
import sys
import json
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, errors="replace")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from questionnaire_client import QuestionnaireClient


def test_questionnaire_api():
    """Test questionnaire API with campaign_id."""
    
    print("=" * 60)
    print("Testing Questionnaire API Integration")
    print("=" * 60)
    
    # Check environment variables
    api_url = os.getenv("HIRINGS_API_URL")
    api_key = os.getenv("WEBHOOK_API_KEY")
    
    if not api_url:
        print("❌ HIRINGS_API_URL not set in environment")
        print("   Please set in .env or Render dashboard")
        return False
    
    if not api_key:
        print("❌ WEBHOOK_API_KEY not set in environment")
        print("   Please set in .env or Render dashboard")
        return False
    
    print(f"✅ API URL: {api_url}")
    print(f"✅ API Key: {api_key[:10]}...")
    print()
    
    # Test campaign_id (from your example)
    campaign_id = "255"
    
    try:
        print(f"📡 Fetching questionnaire for campaign_id={campaign_id}...")
        
        client = QuestionnaireClient(api_base_url=api_url, api_key=api_key)
        questionnaire = client.get_questionnaire_sync(campaign_id)
        
        print("✅ Successfully fetched questionnaire!")
        print()
        print("📋 Questionnaire Summary:")
        print(f"   - Protocol ID: {questionnaire.get('id', 'N/A')}")
        print(f"   - Protocol Name: {questionnaire.get('name', 'N/A')}")
        print(f"   - Pages: {len(questionnaire.get('pages', []))}")
        
        total_prompts = sum(len(page.get('prompts', [])) for page in questionnaire.get('pages', []))
        print(f"   - Total Prompts: {total_prompts}")
        print()
        
        # Save to file for inspection
        output_file = Path("Output") / f"questionnaire_campaign_{campaign_id}.json"
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(questionnaire, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved to: {output_file}")
        print()
        print("✅ Test PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_webhook_simulation():
    """Simulate full webhook processing with campaign_id."""
    
    print()
    print("=" * 60)
    print("Testing Full Webhook Pipeline with campaign_id")
    print("=" * 60)
    
    # Load test webhook
    test_webhook_path = Path("Input2/elevenlabs_webhook_test.json")
    
    if not test_webhook_path.exists():
        print(f"❌ Test webhook not found: {test_webhook_path}")
        return False
    
    with open(test_webhook_path, 'r', encoding='utf-8') as f:
        webhook_data = json.load(f)
    
    # Add campaign_id to dynamic_variables
    if "data" not in webhook_data:
        webhook_data["data"] = {}
    if "conversation_initiation_client_data" not in webhook_data["data"]:
        webhook_data["data"]["conversation_initiation_client_data"] = {}
    if "dynamic_variables" not in webhook_data["data"]["conversation_initiation_client_data"]:
        webhook_data["data"]["conversation_initiation_client_data"]["dynamic_variables"] = {}
    
    webhook_data["data"]["conversation_initiation_client_data"]["dynamic_variables"]["campaign_id"] = "255"
    webhook_data["data"]["conversation_initiation_client_data"]["dynamic_variables"]["company_name"] = "Agaplesion Elisabethenstift Darmstadt gGmbH"
    webhook_data["data"]["conversation_initiation_client_data"]["dynamic_variables"]["candidate_first_name"] = "Max"
    webhook_data["data"]["conversation_initiation_client_data"]["dynamic_variables"]["candidate_last_name"] = "Mustermann"
    
    print("📝 Modified test webhook with campaign_id=255")
    print()
    
    try:
        from pipeline_processor import process_elevenlabs_call
        
        print("🚀 Processing webhook through pipeline...")
        result = process_elevenlabs_call(webhook_data)
        
        print("✅ Pipeline completed successfully!")
        print()
        print("📊 Results:")
        print(f"   - Conversation ID: {result['conversation_id']}")
        print(f"   - Campaign ID: {result.get('campaign_id', 'N/A')}")
        print(f"   - Protocol Source: {result.get('protocol_source', 'N/A')}")
        print(f"   - Applicant ID: {result['applicant_id']}")
        print(f"   - Experiences: {result['experiences_count']}")
        print(f"   - Educations: {result['educations_count']}")
        print()
        print("✅ Full pipeline test PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Pipeline test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Load .env if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("⚠️  python-dotenv not installed, using existing env vars")
    
    success = True
    
    # Test 1: API Connection
    if not test_questionnaire_api():
        success = False
    
    # Test 2: Full Pipeline (only if API test passed)
    if success and not test_full_webhook_simulation():
        success = False
    
    print()
    print("=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)
    
    sys.exit(0 if success else 1)

