#!/usr/bin/env python3
"""
Test queries for the RAG system to validate functionality
"""

from query_rag import RAGQuery
import json
from datetime import datetime

def run_test_queries():
    """Run a set of test queries to validate the RAG system"""
    
    test_questions = [
        # Component-related queries
        "What are the main components of the hydraulic system?",
        "How do I troubleshoot low hydraulic pressure?",
        "What tools are needed for hydraulic pump maintenance?",
        
        # Safety queries
        "What safety procedures should be followed when working on electrical systems?",
        "What are the lockout/tagout procedures?",
        
        # Diagnostic queries
        "What are common symptoms of hydraulic system failure?",
        "How do I diagnose steering system issues?",
        "What error codes indicate electrical problems?",
        
        # Maintenance queries
        "What is the maintenance schedule for the hydraulic system?",
        "How often should hydraulic fluid be changed?",
        "What are the torque specifications for hydraulic fittings?",
        
        # Operational queries
        "What is the proper startup procedure?",
        "How do I perform an emergency shutdown?",
        "What are the operating temperature limits?"
    ]
    
    print("🧪 Running RAG System Test Queries")
    print("=" * 60)
    
    rag = RAGQuery()
    results = []
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n📌 Test {i}/{len(test_questions)}")
        print(f"❓ Question: {question}")
        
        try:
            response = rag.query(question)
            success = not response.startswith("❌")
            
            results.append({
                "test_number": i,
                "question": question,
                "success": success,
                "response_length": len(response),
                "response_preview": response[:200] + "..." if len(response) > 200 else response
            })
            
            print(f"✅ Success: {success}")
            print(f"📏 Response length: {len(response)} characters")
            
        except Exception as e:
            results.append({
                "test_number": i,
                "question": question,
                "success": False,
                "error": str(e)
            })
            print(f"❌ Error: {e}")
    
    # Generate summary
    successful_tests = sum(1 for r in results if r.get("success", False))
    
    summary = {
        "test_date": datetime.now().isoformat(),
        "total_tests": len(test_questions),
        "successful_tests": successful_tests,
        "failed_tests": len(test_questions) - successful_tests,
        "success_rate": f"{(successful_tests/len(test_questions)*100):.1f}%",
        "results": results
    }
    
    # Save results
    output_file = "rag_test_results.json"
    with open(output_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    print(f"✅ Successful: {successful_tests}/{len(test_questions)}")
    print(f"❌ Failed: {len(test_questions) - successful_tests}")
    print(f"📈 Success Rate: {summary['success_rate']}")
    print(f"💾 Results saved to: {output_file}")
    
    return summary


if __name__ == "__main__":
    run_test_queries()