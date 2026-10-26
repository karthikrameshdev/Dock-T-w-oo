"""Local semantic stagnation review before Brain performs targeted recovery."""
import json


class RecoveryExhausted(RuntimeError):pass


class ProgressReviewer:
    def __init__(self,semantic=None):self.semantic=semantic

    def inspect(self, question, error, previous='', attempt=0):
        text=error.casefold()
        if any(word in text for word in ('unauthorized','invalid api key','authentication','missing api key')):
            return {'recoverable':False,'instruction':'The selected model needs valid authentication. Do not retry the same credential.','semantic_similarity':None}
        similarity=self.semantic.similarity(error,previous) if previous and self.semantic and self.semantic.ready else None
        if any(word in text for word in ('argument','schema','unsupported value','unknown tool')):
            hint='Re-read the available tool schema. Use only documented argument names and valid enum values. Choose a different valid action.'
        elif any(word in text for word in ('not exist','not found','no such file')):
            hint='List the containing folder or installed applications first. Use the returned exact path or identifier. Do not retry the missing path.'
        elif any(word in text for word in ('observation','control','focused','desktop')):
            hint='Get a fresh desktop observation, inspect editable controls and use the observed ids. Prefer one open_app call with text for supported editors.'
        else:
            hint='Inspect the actual last result. Change the approach, gather missing evidence, or ask one specific necessary follow-up. Never repeat an unchanged failed action or claim success.'
        return {'recoverable':True,'instruction':hint,'semantic_similarity':similarity,'attempt':attempt,'request':question[:1200],'error':error[:2000]}
