from schema.models import UserProfile, ScoringItem

class CriteriaGenerator:
    def __init__(self):
        pass

    def generate_criteria(self, profile: UserProfile) -> list[ScoringItem]:
        """Generates comparison points (criteria) for insurance policies based on the user's profile and goals."""
        return []