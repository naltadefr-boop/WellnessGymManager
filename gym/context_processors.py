from .models import Parametres, Presence


def contexte_global(request):
    ctx = {"params": Parametres.get()}
    if request.user.is_authenticated:
        ctx["nb_presents"] = Presence.objects.filter(statut=Presence.Statut.EN_COURS).count()
        if request.user.voit_finances:
            from .services import transactions_impayees_qs
            ctx["nb_impayes"] = transactions_impayees_qs().count()
    return ctx
