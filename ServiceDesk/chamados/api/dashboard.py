from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, OuterRef, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from chamados.models import Chamado, HistoricoChamado

from .permissions import IsStaff

PERIODOS = ("hoje", "7d", "30d", "mes", "tudo")
LIMITE_DIARIO_DIAS = 92  # acima disso a evolucao e agrupada por mes
ATIVOS = ("aberto", "andamento")
LIMITE_RECENTES = 100


def _intervalo(periodo):
    # Devolve (inicio, fim) do periodo; fim e exclusivo.
    hoje = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    fim = hoje + timedelta(days=1)
    if periodo == "tudo":
        primeiro = Chamado.objects.order_by("data_criacao").values_list("data_criacao", flat=True).first()
        if primeiro is None:
            return hoje, fim
        return timezone.localtime(primeiro).replace(hour=0, minute=0, second=0, microsecond=0), fim
    if periodo == "hoje":
        return hoje, fim
    if periodo == "30d":
        return hoje - timedelta(days=29), fim
    if periodo == "mes":
        return hoje.replace(day=1), fim
    return hoje - timedelta(days=6), fim


def _variacao(atual, anterior):
    if not anterior:
        return None if not atual else 100.0
    return round((atual - anterior) / anterior * 100, 1)


class DashboardMetricsView(APIView):
    """GET /api/v1/dashboard/metrics/?periodo=hoje|7d|30d|mes|tudo (somente staff).

    A data de conclusao de um chamado e a ultima mudanca de status para
    "Concluido" registrada no HistoricoChamado.
    """

    permission_classes = [IsStaff]

    def get(self, request):
        periodo = request.query_params.get("periodo", "7d")
        if periodo not in PERIODOS:
            periodo = "7d"
        inicio, fim = _intervalo(periodo)
        # Periodo anterior com a mesma duracao, usado nos indicadores de variacao.
        # "tudo" nao tem periodo anterior para comparar.
        comparar = periodo != "tudo"
        ini_ant, fim_ant = inicio - (fim - inicio), inicio

        conclusao = (
            HistoricoChamado.objects.filter(
                chamado=OuterRef("pk"), atributo="Status", valor_novo="Concluido"
            )
            .order_by("-data")
            .values("data")[:1]
        )
        base = Chamado.objects.annotate(data_conclusao=Subquery(conclusao))
        concluidos = base.filter(status="concluido", data_conclusao__isnull=False)

        # Cancelados aparecem na tabela e por status, mas nao contam como chamados abertos.
        criados_todos = base.filter(data_criacao__gte=inicio, data_criacao__lt=fim)
        criados = criados_todos.exclude(status="cancelado")
        criados_ant = base.filter(data_criacao__gte=ini_ant, data_criacao__lt=fim_ant).exclude(status="cancelado")
        cancelados = base.filter(status="cancelado", data_cancelamento__gte=inicio, data_cancelamento__lt=fim)
        resolvidos = concluidos.filter(data_conclusao__gte=inicio, data_conclusao__lt=fim)
        resolvidos_ant = concluidos.filter(data_conclusao__gte=ini_ant, data_conclusao__lt=fim_ant)

        def tma(qs):
            media = qs.annotate(
                duracao=ExpressionWrapper(F("data_conclusao") - F("data_criacao"), output_field=DurationField())
            ).aggregate(m=Avg("duracao"))["m"]
            return round(media.total_seconds() / 3600, 1) if media else None

        n_criados, n_criados_ant = criados.count(), criados_ant.count()
        n_res, n_res_ant = resolvidos.count(), resolvidos_ant.count()

        # Evolucao diaria: abertos x resolvidos, incluindo os dias sem movimento.
        ab_dia = dict(criados.annotate(d=TruncDate("data_criacao")).values_list("d").annotate(n=Count("id")))
        re_dia = dict(resolvidos.annotate(d=TruncDate("data_conclusao")).values_list("d").annotate(n=Count("id")))
        por_mes = (fim - inicio).days > LIMITE_DIARIO_DIAS
        evolucao = []
        if por_mes:
            def mes(d):
                return d.replace(day=1)
            ab_mes, re_mes = {}, {}
            for d, n in ab_dia.items():
                ab_mes[mes(d)] = ab_mes.get(mes(d), 0) + n
            for d, n in re_dia.items():
                re_mes[mes(d)] = re_mes.get(mes(d), 0) + n
            m, ultimo = mes(inicio.date()), mes(fim.date() - timedelta(days=1))
            while m <= ultimo:
                evolucao.append({"data": m.isoformat(), "abertos": ab_mes.get(m, 0), "resolvidos": re_mes.get(m, 0)})
                m = (m + timedelta(days=32)).replace(day=1)
        else:
            dia = inicio.date()
            while dia < fim.date():
                evolucao.append({"data": dia.isoformat(), "abertos": ab_dia.get(dia, 0), "resolvidos": re_dia.get(dia, 0)})
                dia += timedelta(days=1)

        por_status = {s: 0 for s, _ in Chamado.STATUS_CHOICES}
        for linha in criados_todos.values("status").annotate(n=Count("id")):
            por_status[linha["status"]] = linha["n"]

        por_categoria = list(
            criados.values(nome=F("categoria__nome")).annotate(total=Count("id")).order_by("-total")[:8]
        )
        por_solicitante = list(
            criados.values(nome=F("usuario__username")).annotate(total=Count("id")).order_by("-total")[:8]
        )

        recentes = [
            {
                "id": c.id,
                "titulo": c.titulo,
                "solicitante": c.usuario.username,
                "categoria": c.categoria.nome,
                "prioridade": c.prioridade,
                "status": c.status,
                "data_criacao": c.data_criacao,
            }
            for c in criados_todos.select_related("usuario", "categoria").order_by("-data_criacao")[:LIMITE_RECENTES]
        ]

        return Response({
            "periodo": {"chave": periodo, "inicio": inicio.date(), "fim": (fim - timedelta(days=1)).date()},
            "kpis": {
                "ativos": Chamado.objects.filter(status__in=ATIVOS).count(),
                "abertos_periodo": n_criados,
                "abertos_variacao": _variacao(n_criados, n_criados_ant) if comparar else None,
                "criticos": Chamado.objects.filter(status__in=ATIVOS, prioridade="alta").count(),
                "tma_horas": tma(resolvidos),
                "tma_horas_anterior": tma(resolvidos_ant) if comparar else None,
                "resolvidos": n_res,
                "resolvidos_anterior": n_res_ant,
                "resolvidos_variacao": _variacao(n_res, n_res_ant) if comparar else None,
                "cancelados": cancelados.count(),
            },
            "por_status": por_status,
            "evolucao": evolucao,
            "granularidade": "mes" if por_mes else "dia",
            "por_categoria": por_categoria,
            "por_solicitante": por_solicitante,
            "recentes": recentes,
            "total_periodo": criados_todos.count(),
        })
