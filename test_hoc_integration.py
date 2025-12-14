"""
Test script for HOC API integration with 3 separate endpoints.

Usage:
    python test_hoc_integration.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hoc_client import HOCClient


def load_test_data():
    """Load test data from Output directory or use mock data."""
    output_dir = Path("Output")
    
    # Try to find existing files
    protocol_files = sorted(output_dir.glob("protocol_*.json"))
    resume_files = sorted(output_dir.glob("resume_*.json"))
    metadata_files = sorted(output_dir.glob("metadata_*.json"))
    
    if protocol_files and resume_files and metadata_files:
        # Load real data
        with open(protocol_files[-1], 'r', encoding='utf-8') as f:
            protocol = json.load(f)
        
        with open(resume_files[-1], 'r', encoding='utf-8') as f:
            resume_data = json.load(f)
        
        with open(metadata_files[-1], 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Extract conversation_id from filename
        conversation_id = protocol_files[-1].stem.replace("protocol_", "")
        
        return {
            "conversation_id": conversation_id,
            "campaign_id": str(protocol.get("campaign_id", "255")),
            "applicant_id": resume_data.get("applicant", {}).get("id"),
            "applicant": resume_data.get("applicant", {}),
            "resume": resume_data.get("resume", {}),
            "protocol_minimal": protocol,
            "protocol_source": metadata.get("protocol_source", "api_campaign_255"),
            "metadata": metadata
        }
    else:
        # Return mock data
        print("⚠️  No real data found in Output/. Using mock data.")
        return {
            "conversation_id": "conv_test_mock_12345",
            "campaign_id": "255",
            "applicant_id": 89778,
            "applicant": {
                "id": 89778,
                "first_name": "David",
                "last_name": "Jekal",
                "email": "test@example.com",
                "phone": "+4915204465582",
                "postal_code": "64283"
            },
            "resume": {
                "id": 90778,
                "preferred_contact_time": "Nachmittags 15-18 Uhr",
                "preferred_workload": "Part-time",
                "willing_to_relocate": "ja",
                "earliest_start": "2026-01-15",
                "current_job": None,
                "motivation": "Umzug nach Darmstadt, Nähe zur Familie",
                "expectations": "Harmonisches Team, Entwicklungsmöglichkeiten",
                "experiences": [
                    {
                        "id": 1,
                        "title": "Pflegefachkraft",
                        "company": "Klinikum Braunschweig",
                        "location": "Braunschweig",
                        "start": "2022-12-01",
                        "end": "2024-10-31",
                        "current": False,
                        "tasks": "- Arbeit in verschiedenen Stationen (OP, Innere Medizin)\n- OP-Assistenz und allgemeine Pflegetätigkeiten\n- Organisatorische Aufgaben und Patientenbetreuung"
                    }
                ],
                "educations": [
                    {
                        "id": 1,
                        "degree": "Ausbildung zur Pflegefachkraft",
                        "institution": "Klinikum Braunschweig",
                        "location": "Braunschweig",
                        "start": "2019-10-01",
                        "end": "2023-10-31",
                        "current": False
                    }
                ]
            },
            "protocol_minimal": {
                "id": 255,
                "name": "Protokoll - Standort",
                "campaign_id": "255",
                "conversation_id": "conv_test_mock_12345",
                "pages": [
                    {
                        "id": 10,
                        "name": "Standort",
                        "position": 1,
                        "prompts": [
                            {
                                "id": 67,
                                "question": "An welchem Standort möchten Sie arbeiten?",
                                "checked": True
                            }
                        ]
                    }
                ]
            },
            "protocol_source": "api_campaign_255",
            "metadata": {
                "conversation_id": "conv_test_mock_12345",
                "campaign_id": "255",
                "applicant_id": 89778,
                "protocol_source": "api_campaign_255",
                "elevenlabs": {
                    "agent_id": "agent_mock_test",
                    "call_duration_secs": 245,
                    "start_time_unix_secs": 1733988796,
                    "cost_cents": 12,
                    "call_summary": "Test call summary",
                    "termination_reason": "natural end",
                    "candidate_first_name": "David",
                    "candidate_last_name": "Jekal",
                    "company_name": "Test Klinikum",
                    "to_number": "+4915204465582",
                    "agent_phone_number_id": "phnum_test"
                },
                "temporal_context": {
                    "call_date": "2025-12-12",
                    "call_year": 2025,
                    "mentioned_years": [2019, 2022, 2023, 2024]
                },
                "processing": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "experiences_count": 1,
                    "educations_count": 1,
                    "protocol_pages_count": 1,
                    "protocol_prompts_count": 1
                },
                "files": {
                    "protocol": "protocol_conv_test_mock_12345.json",
                    "resume": "resume_89778.json",
                    "metadata": "metadata_conv_test_mock_12345.json"
                }
            }
        }


async def test_hoc_integration():
    """Test HOC API integration with all 3 endpoints."""
    print("\n" + "="*60)
    print("🧪 HOC API Integration Test")
    print("="*60)
    
    # Check environment variables
    api_url = os.getenv("HOC_API_URL")
    api_key = os.getenv("HOC_API_KEY")
    
    print(f"\n📋 Configuration:")
    print(f"   HOC_API_URL: {api_url or '❌ NOT SET'}")
    print(f"   HOC_API_KEY: {'✅ SET' if api_key else '❌ NOT SET'}")
    
    if not api_url or not api_key:
        print("\n⚠️  HOC API not configured. Set HOC_API_URL and HOC_API_KEY environment variables.")
        print("\nExample:")
        print('   export HOC_API_URL="https://high-office.hirings.cloud/api/v1"')
        print('   export HOC_API_KEY="your_token_here"')
        return
    
    # Load test data
    print("\n📂 Loading test data...")
    data = load_test_data()
    
    print(f"   Conversation ID: {data['conversation_id']}")
    print(f"   Campaign ID: {data['campaign_id']}")
    print(f"   Applicant ID: {data['applicant_id']}")
    
    # Initialize client
    client = HOCClient()
    
    # Test all 3 endpoints
    print("\n🚀 Sending data to HOC API (3 endpoints)...")
    print("-" * 60)
    
    try:
        results = await client.send_applicant(data)
        
        # Display results
        print("\n📊 Results:")
        print("-" * 60)
        
        for endpoint, result in results.items():
            if "error" in result:
                print(f"\n❌ {endpoint.upper()}: FAILED")
                print(f"   Error: {result['error']}")
                if "status_code" in result:
                    print(f"   Status Code: {result['status_code']}")
            else:
                print(f"\n✅ {endpoint.upper()}: SUCCESS")
                print(f"   Response: {json.dumps(result, indent=2, ensure_ascii=False)[:200]}...")
        
        # Summary
        success_count = sum(1 for r in results.values() if "error" not in r)
        print("\n" + "="*60)
        print(f"📈 Summary: {success_count}/3 endpoints succeeded")
        print("="*60)
        
        if success_count == 3:
            print("\n🎉 All endpoints successful!")
        elif success_count > 0:
            print(f"\n⚠️  Partial success: {success_count}/3 endpoints")
        else:
            print("\n❌ All endpoints failed")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    # Fix encoding for Windows console
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    asyncio.run(test_hoc_integration())


if __name__ == "__main__":
    main()

