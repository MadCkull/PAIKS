import json
import logging
from django.http import JsonResponse
from django.utils import timezone
from api.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)

def list_sessions(request):
    """GET /api/chat/sessions - Returns all chat sessions"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    sessions = ChatSession.objects.all().order_by('-updated_at')[:50]
    data = []
    for s in sessions:
        data.append({
            'id': s.id,
            'title': s.title,
            'createdAt': int(s.created_at.timestamp() * 1000),
            'updatedAt': int(s.updated_at.timestamp() * 1000),
        })
    return JsonResponse({'sessions': data})

def create_session(request):
    """POST /api/chat/sessions - Creates a new chat session"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        payload = json.loads(request.body)
        title = payload.get('title', 'New Chat')
        import time
        # Match frontend format: sid-<timestamp>
        sid = payload.get('id') or f"sid-{int(time.time() * 1000)}"
        
        session = ChatSession.objects.create(
            id=sid,
            title=title[:255]
        )
        return JsonResponse({
            'id': session.id,
            'title': session.title,
            'createdAt': int(session.created_at.timestamp() * 1000)
        })
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def get_session_messages(request, session_id):
    """GET /api/chat/sessions/<id>/messages"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        session = ChatSession.objects.get(id=session_id)
        messages = session.messages.all().order_by('created_at')
        
        data = []
        for m in messages:
            data.append({
                'id': m.id,
                'role': m.role,
                'text': m.content,
                'metadata': m.metadata,
                'time': int(m.created_at.timestamp() * 1000)
            })
        return JsonResponse({'messages': data})
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def delete_session(request, session_id):
    """DELETE /api/chat/sessions/<id>"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        ChatSession.objects.filter(id=session_id).delete()
        return JsonResponse({'status': 'deleted'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
