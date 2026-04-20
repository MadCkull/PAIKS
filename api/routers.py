class ChatRouter:
    """
    A router to control all database operations on models in the
    api application for chat components.
    """
    route_app_labels = {'api'}
    
    def _is_chat_model(self, model_name):
        return model_name in ('chatsession', 'chatmessage')

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'api':
            if self._is_chat_model(model._meta.model_name):
                return 'chats'
            return 'default'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'api':
            if self._is_chat_model(model._meta.model_name):
                return 'chats'
            return 'default'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations if both belong to the same db
        if obj1._meta.app_label == 'api' and obj2._meta.app_label == 'api':
            is_obj1_chat = self._is_chat_model(obj1._meta.model_name)
            is_obj2_chat = self._is_chat_model(obj2._meta.model_name)
            if is_obj1_chat == is_obj2_chat:
                return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'api':
            if model_name and self._is_chat_model(model_name):
                return db == 'chats'
            else:
                return db == 'default'
        return None
