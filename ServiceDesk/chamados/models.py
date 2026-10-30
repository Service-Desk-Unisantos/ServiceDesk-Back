from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify


class Categoria(models.Model):
    # Categorias cadastradas pelos administradores e oferecidas na abertura de chamado (RF03).
    nome = models.CharField(max_length=50, unique=True)
    # Identificador fixo usado pelos chamados e pela API; nao muda ao renomear a categoria.
    slug = models.SlugField(max_length=50, unique=True, editable=False)
    # Categoria inativa some do formulario, mas continua nos chamados antigos.
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class Chamado(models.Model):
    # Status para acompanhamento do atendimento (RF05).
    STATUS_CHOICES = [
        ("aberto", "Aberto"),
        ("andamento", "Em andamento"),
        ("concluido", "Concluido"),
    ]

    # Prioridade definida no momento da abertura do chamado.
    PRIORIDADE_CHOICES = [
        ("baixa", "Baixa"),
        ("media", "Media"),
        ("alta", "Alta"),
    ]

    titulo = models.CharField(max_length=100)
    descricao = models.TextField()
    # Categoria da solicitacao, exigida no requisito de registro (RF03).
    # PROTECT impede excluir categoria em uso; o caminho e desativa-la.
    categoria = models.ForeignKey(
        Categoria,
        to_field="slug",
        on_delete=models.PROTECT,
        related_name="chamados",
    )
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aberto")
    prioridade = models.CharField(max_length=20, choices=PRIORIDADE_CHOICES)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Exibe os chamados mais recentes primeiro no painel.
        ordering = ["-data_criacao"]

    def __str__(self):
        return self.titulo


class Comentario(models.Model):
    # Relacionamento entre comentarios e chamado.
    chamado = models.ForeignKey(
        Chamado, on_delete=models.CASCADE, related_name="comentarios"
    )
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    texto = models.TextField()
    data = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario} - {self.chamado}"


class Notificacao(models.Model):
    # Notificacao persistida para entrega por polling HTTP sem depender de WebSocket.
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    chamado = models.ForeignKey(
        Chamado,
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    tipo = models.CharField(max_length=50)
    mensagem = models.TextField()
    lida = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criada_em", "-id"]

    def __str__(self):
        return f"{self.usuario} - {self.tipo}"


class HistoricoChamado(models.Model):
    # Registro de auditoria: cada criacao, edicao e comentario do chamado.
    ACAO_CRIOU = "criou"
    ACAO_EDITOU = "editou"
    ACAO_COMENTOU = "comentou"
    ACAO_CHOICES = [
        (ACAO_CRIOU, "Criou"),
        (ACAO_EDITOU, "Editou"),
        (ACAO_COMENTOU, "Comentou"),
    ]

    chamado = models.ForeignKey(
        Chamado, on_delete=models.CASCADE, related_name="historico"
    )
    # SET_NULL preserva o registro mesmo se o usuario for removido.
    autor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    acao = models.CharField(max_length=20, choices=ACAO_CHOICES)
    atributo = models.CharField(max_length=50)
    valor_anterior = models.CharField(max_length=255, blank=True, default="")
    valor_novo = models.CharField(max_length=255, blank=True, default="")
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-id"]

    def __str__(self):
        return f"{self.chamado_id} - {self.acao} {self.atributo}"


def _resumo(texto, limite=255):
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def registrar_edicoes(chamado, autor, antes):
    # Compara os campos editaveis com o estado anterior e grava uma linha por mudanca.
    # `antes` e um dict {"status": ..., "prioridade": ...} capturado antes de salvar.
    for campo, rotulo in (("status", "Status"), ("prioridade", "Prioridade")):
        if antes.get(campo) == getattr(chamado, campo):
            continue
        HistoricoChamado.objects.create(
            chamado=chamado,
            autor=autor,
            acao=HistoricoChamado.ACAO_EDITOU,
            atributo=rotulo,
            valor_anterior=dict(chamado._meta.get_field(campo).choices).get(
                antes.get(campo), antes.get(campo) or ""
            ),
            valor_novo=getattr(chamado, f"get_{campo}_display")(),
        )


@receiver(post_save, sender=Chamado)
def _historico_criacao(sender, instance, created, **kwargs):
    if created:
        HistoricoChamado.objects.create(
            chamado=instance,
            autor=instance.usuario,
            acao=HistoricoChamado.ACAO_CRIOU,
            atributo="Chamado",
            valor_novo=_resumo(instance.titulo),
        )


@receiver(post_save, sender=Comentario)
def _historico_comentario(sender, instance, created, **kwargs):
    if created:
        HistoricoChamado.objects.create(
            chamado=instance.chamado,
            autor=instance.usuario,
            acao=HistoricoChamado.ACAO_COMENTOU,
            atributo="Comentário",
            valor_novo=_resumo(instance.texto),
        )
