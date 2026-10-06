import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from datetime import datetime

os.environ["PORT"] = "8080"

# Configuração
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Arquivos de dados
ARQUIVO_PRODUTOS = "produtos.json"
ARQUIVO_TICKETS = "tickets.json"
ARQUIVO_RANK = "rank.json"

# Carregar dados
def carregar_arquivo(arquivo, padrao):
    if os.path.exists(arquivo):
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)
    return padrao

def salvar_arquivo(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

produtos = carregar_arquivo(ARQUIVO_PRODUTOS, [])
tickets = carregar_arquivo(ARQUIVO_TICKETS, {})
rank = carregar_arquivo(ARQUIVO_RANK, {})

# IDs que você edita abaixo
STAFF_ROLE_ID = 0  # Cola aqui o ID do cargo da equipe
CATEGORIA_TICKET_ID = 0  # Cola aqui o ID da categoria dos tickets
CANAL_LOG_ID = 0  # Cola aqui o ID do canal de logs

# ------------------------------
# EVENTO BOT LIGADO
# ------------------------------
@bot.event
async def on_ready():
    print(f"✅ Bot ligado como {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos sincronizados!")
    except Exception as e:
        print(f"❌ Erro: {e}")

# ------------------------------
# SISTEMA DE LOJA
# ------------------------------
@bot.tree.command(name="criar_produto", description="Cria um produto (Admin)")
@app_commands.describe(nome="Nome do produto", preco="Preço", descricao="Descrição")
async def criar_produto(interaction: discord.Interaction, nome: str, preco: float, descricao: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Sem permissão!", ephemeral=True)
    
    produtos.append({
        "id": len(produtos)+1,
        "nome": nome,
        "preco": preco,
        "descricao": descricao
    })
    salvar_arquivo(ARQUIVO_PRODUTOS, produtos)
    
    embed = discord.Embed(title="✅ Produto Criado!", color=discord.Color.green())
    embed.add_field(name="Nome", value=nome, inline=False)
    embed.add_field(name="Preço", value=f"R$ {preco:.2f}", inline=False)
    embed.add_field(name="Descrição", value=descricao, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="lista_produtos", description="Ver todos os produtos")
async def lista_produtos(interaction: discord.Interaction):
    if not produtos:
        return await interaction.response.send_message("❌ Nenhum produto cadastrado!", ephemeral=True)
    
    embed = discord.Embed(title="🛒 Nossos Produtos", color=discord.Color.blue())
    for p in produtos:
        embed.add_field(
            name=f"#{p['id']} — {p['nome']}",
            value=f"💵 R$ {p['preco']:.2f}\n{p['descricao']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

# Botão de comprar
class ComprarView(discord.ui.View):
    def __init__(self, produto):
        super().__init__(timeout=None)
        self.produto = produto

    @discord.ui.button(label="🛒 Comprar Agora", style=discord.ButtonStyle.green, custom_id="comprar_btn")
    async def comprar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Criar ticket de compra
        categoria = interaction.guild.get_channel(CATEGORIA_TICKET_ID) or discord.utils.get(interaction.guild.categories, name="TICKETS")
        if not categoria:
            categoria = await interaction.guild.create_category("TICKETS")
        
        # Verificar se já tem ticket aberto
        for ch in categoria.channels:
            if ch.topic and str(interaction.user.id) in ch.topic:
                return await interaction.response.send_message(f"❌ Você já tem um ticket aberto: {ch.mention}", ephemeral=True)
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        
        canal = await categoria.create_text_channel(
            f"compra-{interaction.user.name}",
            overwrites=overwrites,
            topic=f"ticket:{interaction.user.id}:{self.produto['id']}"
        )
        
        tickets[str(canal.id)] = {
            "usuario": interaction.user.id,
            "produto": self.produto,
            "status": "aberto",
            "data": str(datetime.now())
        }
        salvar_arquivo(ARQUIVO_TICKETS, tickets)
        
        embed = discord.Embed(title="🛒 Pedido Recebido!", color=discord.Color.green())
        embed.add_field(name="Produto", value=self.produto["nome"], inline=False)
        embed.add_field(name="Valor", value=f"R$ {self.produto['preco']:.2f}", inline=False)
        embed.add_field(name="Comprador", value=interaction.user.mention, inline=False)
        embed.set_footer(text="A equipe vai te atender em breve!")
        
        await canal.send(f"{interaction.user.mention} | <@&{STAFF_ROLE_ID}>", embed=embed, view=FecharTicketView())
        await interaction.response.send_message(f"✅ Ticket criado: {canal.mention}", ephemeral=True)

@bot.tree.command(name="ver_produto", description="Ver produto e botão de compra")
@app_commands.describe(id="ID do produto")
async def ver_produto(interaction: discord.Interaction, id: int):
    prod = next((p for p in produtos if p["id"] == id), None)
    if not prod:
        return await interaction.response.send_message("❌ Produto não encontrado!", ephemeral=True)
    
    embed = discord.Embed(title=prod["nome"], color=discord.Color.green())
    embed.add_field(name="Preço", value=f"💵 R$ {prod['preco']:.2f}", inline=False)
    embed.add_field(name="Descrição", value=prod["descricao"], inline=False)
    await interaction.response.send_message(embed=embed, view=ComprarView(prod))

# ------------------------------
# SISTEMA DE TICKET
# ------------------------------
class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fechar Ticket", style=discord.ButtonStyle.red, custom_id="fechar_ticket")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("❌ Sem permissão!", ephemeral=True)
        
        tickets[str(interaction.channel.id)]["status"] = "fechado"
        salvar_arquivo(ARQUIVO_TICKETS, tickets)
        
        await interaction.response.send_message("✅ Fechando em 3 segundos...")
        await interaction.channel.delete(reason="Ticket fechado")

@bot.tree.command(name="abrir_ticket", description="Abrir um ticket de suporte")
async def abrir_ticket(interaction: discord.Interaction):
    categoria = discord.utils.get(interaction.guild.categories, name="TICKETS")
    if not categoria:
        categoria = await interaction.guild.create_category("TICKETS")
    
    for ch in categoria.channels:
        if ch.topic and str(interaction.user.id) in ch.topic:
            return await interaction.response.send_message(f"❌ Já tem ticket aberto: {ch.mention}", ephemeral=True)
    
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        interaction.guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }
    
    canal = await categoria.create_text_channel(
        f"ticket-{interaction.user.name}",
        overwrites=overwrites,
        topic=f"ticket:{interaction.user.id}"
    )
    
    tickets[str(canal.id)] = {
        "usuario": interaction.user.id,
        "tipo": "suporte",
        "status": "aberto",
        "data": str(datetime.now())
    }
    salvar_arquivo(ARQUIVO_TICKETS, tickets)
    
    embed = discord.Embed(title="🎫 Ticket Aberto!", color=discord.Color.blue())
    embed.description = f"{interaction.user.mention}, explique seu problema que a equipe atende!"
    await canal.send(f"{interaction.user.mention} | <@&{STAFF_ROLE_ID}>", embed=embed, view=FecharTicketView())
    await interaction.response.send_message(f"✅ Ticket: {canal.mention}", ephemeral=True)

# ------------------------------
# APAGAR MENSAGENS
# ------------------------------
@bot.tree.command(name="limpar", description="Apaga mensagens (Staff)")
@app_commands.describe(quantidade="Número de mensagens para apagar")
async def limpar(interaction: discord.Interaction, quantidade: int):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("❌ Sem permissão!", ephemeral=True)
    
    if quantidade < 1 or quantidade > 100:
        return await interaction.response.send_message("❌ De 1 a 100 mensagens!", ephemeral=True)
    
    await interaction.channel.purge(limit=quantidade)
    await interaction.response.send_message(f"✅ Apagadas {quantidade} mensagens!", ephemeral=True)

# ------------------------------
# SISTEMA DE RANKING
# ------------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    uid = str(message.author.id)
    if uid not in rank:
        rank[uid] = {"xp": 0, "mensagens": 0, "nivel": 1}
    
    rank[uid]["mensagens"] += 1
    rank[uid]["xp"] += 1
    
    # Calcular nível
    xp_necessario = rank[uid]["nivel"] * 100
    if rank[uid]["xp"] >= xp_necessario:
        rank[uid]["nivel"] += 1
        rank[uid]["xp"] = 0
        await message.channel.send(
            f"🎉 {message.author.mention} subiu para o **Nível {rank[uid]['nivel']}**!",
            delete_after=5
        )
    
    salvar_arquivo(ARQUIVO_RANK, rank)
    await bot.process_commands(message)

@bot.tree.command(name="nivel", description="Ver seu nível")
async def nivel(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    if uid not in rank:
        return await interaction.response.send_message("❌ Nenhum dado encontrado!", ephemeral=True)
    
    dados = rank[uid]
    xp_prox = dados["nivel"] * 100
    porcentagem = int((dados["xp"] / xp_prox) * 100)
    
    embed = discord.Embed(title=f"📊 Nível de {interaction.user.name}", color=discord.Color.gold())
    embed.add_field(name="Nível", value=f"🏆 {dados['nivel']}", inline=True)
    embed.add_field(name="XP", value=f"⭐ {dados['xp']}/{xp_prox}", inline=True)
    embed.add_field(name="Mensagens", value=f"💬 {dados['mensagens']}", inline=True)
    embed.add_field(name="Progresso", value=f"[{'█'*(porcentagem//10)}{'░'*(10-porcentagem//10)}] {porcentagem}%", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ranking", description="Top 10 do servidor")
async def ranking(interaction: discord.Interaction):
    ordenado = sorted(rank.items(), key=lambda x: x[1]["nivel"]*100 + x[1]["xp"], reverse=True)[:10]
    
    embed = discord.Embed(title="🏆 TOP 10 — Ranking", color=discord.Color.gold())
    for i, (uid, dados) in enumerate(ordenado, 1):
        usuario = await bot.fetch_user(int(uid))
        embed.add_field(
            name=f"#{i} {usuario.name}",
            value=f"Nível: {dados['nivel']} | XP: {dados['xp']} | Msg: {dados['mensagens']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

# ------------------------------
# LIGAR O BOT
# ------------------------------
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ Coloca o token nas variáveis do Render!")
