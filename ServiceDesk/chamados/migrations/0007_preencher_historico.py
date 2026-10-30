from django.db import migrations


def preencher(apps, schema_editor):
    # Gera o historico retroativo (criacao + comentarios) dos chamados ja existentes.
    Chamado = apps.get_model("chamados", "Chamado")
    Comentario = apps.get_model("chamados", "Comentario")
    Historico = apps.get_model("chamados", "HistoricoChamado")

    def resumo(texto, limite=255):
        texto = " ".join((texto or "").split())
        return texto if len(texto) <= limite else texto[: limite - 1] + "…"

    for chamado in Chamado.objects.all():
        h = Historico.objects.create(
            chamado=chamado, autor_id=chamado.usuario_id, acao="criou",
            atributo="Chamado", valor_novo=resumo(chamado.titulo),
        )
        Historico.objects.filter(pk=h.pk).update(data=chamado.data_criacao)

    for c in Comentario.objects.all():
        h = Historico.objects.create(
            chamado_id=c.chamado_id, autor_id=c.usuario_id, acao="comentou",
            atributo="Comentário", valor_novo=resumo(c.texto),
        )
        Historico.objects.filter(pk=h.pk).update(data=c.data)


class Migration(migrations.Migration):

    dependencies = [
        ("chamados", "0006_historicochamado"),
    ]

    operations = [
        migrations.RunPython(preencher, migrations.RunPython.noop),
    ]
