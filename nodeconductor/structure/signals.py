from django.dispatch import Signal

# Role related signals
# sender = structure class, e.g. Customer or Project
structure_role_granted = Signal(providing_args=['structure', 'user', 'role'])
structure_role_revoked = Signal(providing_args=['structure', 'user', 'role'])

resource_imported = Signal(providing_args=['instance'])
