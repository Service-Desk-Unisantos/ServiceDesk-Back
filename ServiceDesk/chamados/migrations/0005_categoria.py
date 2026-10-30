import django.db.models.deletion
from django.db import migrations, models

# Categorias que antes eram fixas no codigo (Chamado.CATEGORIA_CHOICES).
CATEGORIAS_INICIAIS = [
    ("hardware", "Hardware"),
    ("software", "Software"),
    ("rede", "Rede"),
    ("acesso", "Acesso"),
    ("outros", "Outros"),
]


def criar_categorias_iniciais(apps, schema_editor):
    Categoria = apps.get_model("chamados", "Categoria")
    for slug, nome in CATEGORIAS_INICIAIS:
        Categoria.objects.get_or_create(slug=slug, defaults={"nome": nome})


def copiar_categoria_dos_chamados(apps, schema_editor):
    Chamado = apps.get_model("chamados", "Chamado")
    Categoria = apps.get_model("chamados", "Categoria")
    slugs_validos = set(Categoria.objects.values_list("slug", flat=True))
    for chamado in Chamado.objects.all():
        slug = chamado.categoria if chamado.categoria in slugs_validos else "outros"
        Chamado.objects.filter(pk=chamado.pk).update(categoria_ref_id=slug)


def restaurar_categoria_dos_chamados(apps, schema_editor):
    Chamado = apps.get_model("chamados", "Chamado")
    for chamado in Chamado.objects.all():
        Chamado.objects.filter(pk=chamado.pk).update(categoria=chamado.categoria_ref_id)


class Migration(migrations.Migration):

    dependencies = [
        ("chamados", "0004_notificacao"),
    ]

    operations = [
        migrations.CreateModel(
            name="Categoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=50, unique=True)),
                ("slug", models.SlugField(editable=False, unique=True)),
                ("ativa", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["nome"],
            },
        ),
        migrations.RunPython(criar_categorias_iniciais, migrations.RunPython.noop),
        migrations.AddField(
            model_name="chamado",
            name="categoria_ref",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="chamados.categoria",
                to_field="slug",
            ),
        ),
        migrations.RunPython(copiar_categoria_dos_chamados, restaurar_categoria_dos_chamados),
        migrations.RemoveField(
            model_name="chamado",
            name="categoria",
        ),
        migrations.RenameField(
            model_name="chamado",
            old_name="categoria_ref",
            new_name="categoria",
        ),
        migrations.AlterField(
            model_name="chamado",
            name="categoria",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="chamados",
                to="chamados.categoria",
                to_field="slug",
            ),
        ),
    ]
