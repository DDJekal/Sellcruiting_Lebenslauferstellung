"""Test HOC API payload structure."""
import sys
import os
import json
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hoc_client import HOCClient

def test_hoc_payload():
    """Test that HOC payload contains all required fields."""
    
    print("=" * 60)
    print("Testing HOC API Payload Structure")
    print("=" * 60)
    
    # Simulate pipeline result
    pipeline_result = {
        "conversation_id": "conv_test123",
        "campaign_id": "255",
        "protocol_source": "api_campaign_255",
        "applicant_id": 12345,
        "resume_id": 12346,
        "applicant": {
            "id": 12345,
            "first_name": "Max",
            "last_name": "Mustermann",
            "email": "max@example.com",
            "phone": "+49123456789",
            "postal_code": "12345"
        },
        "resume": {
            "id": 12346,
            "preferred_contact_time": "Nachmittags",
            "preferred_workload": "Vollzeit",
            "willing_to_relocate": "ja",
            "earliest_start": "2025-01-01",
            "current_job": "Software Engineer",
            "motivation": "- Neue Herausforderung\n- Besseres Gehalt",
            "expectations": "- Homeoffice\n- Weiterbildung",
            "start": "2025-01-01",
            "applicant_id": 12345,
            "experiences": [
                {
                    "id": 1,
                    "start": "2020-01-01",
                    "end": None,
                    "company": "Tech Corp",
                    "tasks": "- Entwicklung von Backend-Services mit Python und FastAPI\n- Design und Implementierung von RESTful APIs\n- Datenbank-Optimierung (PostgreSQL)\n- Code-Reviews und Mentoring von Junior-Entwicklern\n- Deployment mit Docker und Kubernetes"
                }
            ],
            "educations": [
                {
                    "id": 1,
                    "end": "2019-12-31",
                    "company": "TU München",
                    "description": "Bachelor of Science Informatik"
                }
            ]
        },
        "protocol_minimal": {
            "id": 255,
            "name": "Protokoll Test",
            "campaign_id": "255",
            "conversation_id": "conv_test123",
            "pages": [
                {
                    "id": 1,
                    "name": "Qualifikation",
                    "position": 1,
                    "prompts": [
                        {
                            "id": 10,
                            "question": "Haben Sie ein abgeschlossenes Studium?",
                            "position": 1,
                            "checked": True
                        }
                    ]
                }
            ]
        },
        "metadata": {
            "conversation_id": "conv_test123",
            "campaign_id": "255",
            "applicant_id": 12345,
            "protocol_source": "api_campaign_255",
            "elevenlabs": {
                "agent_id": "agent_123",
                "call_duration_secs": 245,
                "start_time_unix_secs": 1733988796,
                "cost_cents": 12,
                "call_successful": True,
                "call_summary": "Test summary",
                "termination_reason": "natural end",
                "candidate_first_name": "Max",
                "candidate_last_name": "Mustermann",
                "company_name": "Test Corp",
                "to_number": "+49123456789",
                "agent_phone_number_id": "phnum_123"
            },
            "temporal_context": {
                "call_date": "2025-12-12",
                "call_year": 2025,
                "call_timestamp": 1733988796,
                "mentioned_years": [2020, 2019],
                "temporal_annotations_count": 5
            },
            "processing": {
                "timestamp": "2025-12-12T10:00:00Z",
                "experiences_count": 1,
                "educations_count": 1,
                "protocol_pages_count": 1,
                "protocol_prompts_count": 1
            },
            "files": {
                "protocol": "protocol_conv_test123.json",
                "resume": "resume_12345.json",
                "metadata": "metadata_conv_test123.json"
            }
        },
        "timestamp": "2025-12-12T10:00:00Z",
        "files": {
            "protocol": "protocol_conv_test123.json",
            "resume": "resume_12345.json",
            "metadata": "metadata_conv_test123.json"
        }
    }
    
    # Create HOC client and prepare payload
    client = HOCClient()
    payload = client._prepare_hoc_payload(pipeline_result)
    
    print("\n📦 HOC Payload Structure:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    # Validate structure
    print("\n✅ Validating payload structure...")
    
    assert "applicant" in payload, "Missing 'applicant'"
    assert "resume" in payload, "Missing 'resume'"
    assert "protocol" in payload, "Missing 'protocol'"
    assert "metadata" in payload, "Missing 'metadata'"
    
    # Validate applicant
    assert payload["applicant"]["id"] == 12345
    assert payload["applicant"]["first_name"] == "Max"
    print("  ✅ Applicant: OK")
    
    # Validate resume
    assert payload["resume"]["id"] == 12346
    assert len(payload["resume"]["experiences"]) == 1
    assert len(payload["resume"]["educations"]) == 1
    
    # Check tasks length
    tasks_length = len(payload["resume"]["experiences"][0]["tasks"])
    print(f"  ✅ Resume: OK (tasks={tasks_length} chars)")
    if tasks_length < 100:
        print(f"  ⚠️  WARNING: Tasks too short ({tasks_length} < 100)")
    
    # Validate protocol (minimal)
    assert payload["protocol"]["id"] == 255
    assert payload["protocol"]["campaign_id"] == "255"
    assert len(payload["protocol"]["pages"]) == 1
    assert "checked" in payload["protocol"]["pages"][0]["prompts"][0]
    assert "value" not in payload["protocol"]["pages"][0]["prompts"][0]  # Minimal!
    print("  ✅ Protocol (minimal): OK")
    
    # Validate metadata
    assert payload["metadata"]["conversation_id"] == "conv_test123"
    assert "elevenlabs" in payload["metadata"]
    assert "temporal_context" in payload["metadata"]
    assert "processing" in payload["metadata"]
    assert "files" in payload["metadata"]
    print("  ✅ Metadata: OK")
    
    print("\n" + "=" * 60)
    print("✅ HOC PAYLOAD TEST PASSED!")
    print("=" * 60)
    
    return payload


if __name__ == "__main__":
    try:
        payload = test_hoc_payload()
        
        # Save for inspection
        output_file = Path("Output") / "hoc_payload_example.json"
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved to: {output_file}")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

