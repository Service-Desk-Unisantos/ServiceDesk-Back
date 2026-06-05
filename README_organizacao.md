# ServiceDesk — Sistema de Gerenciamento de Chamados

Projeto desenvolvido por estudantes da **Universidade Católica de Santos (Unisantos)** como trabalho prático da disciplina PGC-PCE, com objetivo de implementação real em ambiente corporativo.

---

## O que é este projeto?

O **ServiceDesk** é uma plataforma de suporte técnico que permite que colaboradores de uma empresa registrem solicitações de atendimento (chamados) e acompanhem o progresso em tempo real. A equipe de infraestrutura gerencia e resolve cada chamado diretamente pelo sistema.

---

## O problema que resolve

Em ambientes corporativos sem uma ferramenta centralizada, solicitações de suporte chegam por e-mail, mensagens ou verbalmente, dificultando o controle, a priorização e o histórico dos atendimentos. O ServiceDesk centraliza tudo em um único lugar, com rastreabilidade completa.

---

## Funcionalidades principais

- **Abertura de chamados** com título, descrição, categoria e prioridade
- **Painel de acompanhamento** com status atualizado em tempo real
- **Dois perfis de acesso**: cliente (colaborador) e equipe técnica (staff/admin)
- **Notificações automáticas** quando o status de um chamado é alterado
- **Histórico de comunicação** entre cliente e equipe via comentários
- **Login com Google** além do cadastro por usuário e senha
- **API REST** para integração com aplicações externas
- **Monitoramento de custos de infraestrutura** (módulo FinOps)

---

## Repositórios

| Repositório | Descrição |
|-------------|-----------|
| [servicedesk-backend](./servicedesk-backend) | Servidor, regras de negócio, banco de dados e API REST |
| [servicedesk-frontend](./servicedesk-frontend) | Interface do usuário consumindo a API do backend |

---

## Fluxo geral

```
Colaborador abre chamado
        ↓
Técnico analisa, atualiza status e responde
        ↓
Colaborador recebe notificação e acompanha resolução
```

---

## Contexto acadêmico

Este projeto foi desenvolvido como parte do curso de **Graduação em Sistemas de Informação** da Unisantos, com requisitos funcionais mapeados desde a concepção até a implementação. O design considera escalabilidade para uso real em produção.

---

*Unisantos — Santos, SP*
