import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import datetime
from enum import Enum
import plotly.express as px
import plotly.graph_objects as go
import time
import base64

# ==============================================================================
# CONFIGURATION DE LA PAGE
# Doit être la première commande Streamlit
# ==============================================================================
favicon_url = "https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.gva.ch/fr&size=128"
main_logo_url = "https://www.gva.ch/Images/logo-gva.aspx"

st.set_page_config(
    page_title="Portail de demandes - Performance & Forecasting",
    page_icon=favicon_url,
    layout="wide",
    initial_sidebar_state="expanded" 
)

# ==============================================================================
# CONFIGURATION ET ENUMS
# ==============================================================================

class TicketStatus(Enum):
    NOUVEAU = "Nouveau"
    EN_COURS = "En cours"
    EN_ATTENTE = "En attente"
    TESTE = "En test"
    TERMINE = "Terminé"
    REJETE = "Rejeté"

class TicketPriority(Enum):
    CRITIQUE = "Critique"
    ELEVEE = "Élevée"
    NORMALE = "Normale"
    FAIBLE = "Faible"

class TicketType(Enum):
    RAPPORT_WEBI = "Rapport WebI"
    RAPPORT_POWERBI = "Rapport Power BI"
    DASHBOARD = "Dashboard"
    ANALYSE_DONNEES = "Analyse de données"
    CORRECTION_BUG = "Correction de bug"
    FORMATION = "Formation"
    AUTRE = "Autre"

class TicketCategory(Enum):
    OPERATIONNEL = "Opérationnel"
    COMMERCIAL = "Commercial"
    SECURITE = "Sécurité"
    MAINTENANCE = "Maintenance"
    RESSOURCES_HUMAINES = "Ressources Humaines"
    FINANCE = "Finance"
    AUTRE = "Autre"

# ==============================================================================
# STYLE CSS PERSONNALISÉ & RESSOURCES
# ==============================================================================
def load_css():
    st.markdown("""
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <style>
        /* Thème sombre et polices */
        html, body, [class*="st-"] {
            font-family: 'Inter', sans-serif;
        }
        /* Configuration des conteneurs principaux */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        /* Style des cartes KPI */
        .kpi-card {
            background-color: #2F2F4A;
            border: 1px solid #4A4A6A;
            padding: 1.2rem;
            border-radius: 0.5rem;
            text-align: center;
            height: 100%;
        }
        .kpi-label {
            font-size: 1.1rem;
            font-weight: 500;
            color: #A0A0B0; /* Gris clair pour le label */
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem; /* Espace entre l'icône et le texte */
        }
        .kpi-value {
            color: #FFFFFF; /* Blanc pour la valeur */
            font-size: 2.2rem;
            font-weight: bold;
        }
        /* Style des expanders */
        .st-expander-header {
            font-size: 1.1rem !important;
        }
        .st-expander {
            border: 1px solid #4A4A6A;
            border-radius: 0.5rem;
        }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# SECTION BASE DE DONNÉES
# ==============================================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@st.cache_resource
def create_connection(db_file="oop_ticketing_geneva.db"):
    try:
        # Correction de l'erreur de thread en autorisant le partage de la connexion
        return sqlite3.connect(db_file, check_same_thread=False)
    except sqlite3.Error as e:
        st.error(f"Erreur de connexion à la base de données : {e}")
        return None

def create_tables(_conn):
    try:
        c = _conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                email TEXT, full_name TEXT, department TEXT,
                is_analyst INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT, ticket_type TEXT NOT NULL,
                category TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'Normale', status TEXT NOT NULL DEFAULT 'Nouveau',
                business_justification TEXT, expected_delivery DATE, data_sources TEXT,
                technical_requirements TEXT, created_by_id INTEGER, assigned_to_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                estimated_hours INTEGER, actual_hours INTEGER,
                FOREIGN KEY (created_by_id) REFERENCES users (id), FOREIGN KEY (assigned_to_id) REFERENCES users (id)
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY, ticket_id INTEGER, user_id INTEGER, comment TEXT NOT NULL,
                is_internal INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets (id), FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)
        _conn.commit()
    except sqlite3.Error as e:
        print(f"Erreur lors de la création des tables : {e}")

def run_setup():
    conn = create_connection()
    if conn:
        create_tables(conn)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username='oop_admin'")
        if cur.fetchone() is None:
            add_user(conn, 'oop_admin', 'admin123', 'oop-admin@gva.ch', 'Administrateur OOP', 'Performance & Forecasting', is_analyst=True)
        cur.execute("SELECT 1 FROM users WHERE username='test_user'")
        if cur.fetchone() is None:
            add_user(conn, 'test_user', 'test123', 'test@gva.ch', 'Utilisateur Test', 'Opérations')
        # La connexion est gérée par le cache de Streamlit, pas besoin de la fermer ici.

# Fonctions CRUD (Create, Read, Update, Delete)
def add_user(conn, username, password, email=None, full_name=None, department=None, is_analyst=False):
    sql = 'INSERT INTO users(username, password, email, full_name, department, is_analyst) VALUES(?,?,?,?,?,?)'
    try:
        cur = conn.cursor()
        cur.execute(sql, (username, hash_password(password), email, full_name, department, 1 if is_analyst else 0))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None

def get_user(conn, username, password):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND password=?", (username, hash_password(password)))
    return cur.fetchone()

def get_all_analysts(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, username, full_name FROM users WHERE is_analyst=1 ORDER BY full_name")
    return cur.fetchall()

def get_all_users(conn):
    """Récupère tous les utilisateurs pour la gestion."""
    return pd.read_sql_query("SELECT id, full_name, username, email, department, is_analyst FROM users", conn)

def update_user_role(conn, user_id, is_analyst):
    """Met à jour le rôle d'un utilisateur."""
    sql = "UPDATE users SET is_analyst = ? WHERE id = ?"
    cur = conn.cursor()
    cur.execute(sql, (1 if is_analyst else 0, user_id))
    conn.commit()

def delete_user(conn, user_id):
    """Supprime un utilisateur et anonymise ses tickets/commentaires."""
    try:
        cur = conn.cursor()
        # Anonymiser les tickets créés par l'utilisateur
        cur.execute("UPDATE tickets SET created_by_id = NULL WHERE created_by_id = ?", (user_id,))
        # Anonymiser les tickets assignés à l'utilisateur (s'il était analyste)
        cur.execute("UPDATE tickets SET assigned_to_id = NULL WHERE assigned_to_id = ?", (user_id,))
        # Supprimer les commentaires de l'utilisateur
        cur.execute("DELETE FROM comments WHERE user_id = ?", (user_id,))
        # Supprimer l'utilisateur
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Erreur lors de la suppression de l'utilisateur : {e}")


def create_ticket(conn, ticket_data):
    sql = '''INSERT INTO tickets(title, description, ticket_type, category, priority, business_justification, 
                                 expected_delivery, data_sources, technical_requirements, created_by_id, estimated_hours)
             VALUES(?,?,?,?,?,?,?,?,?,?,?)'''
    cur = conn.cursor()
    cur.execute(sql, ticket_data)
    conn.commit()
    return cur.lastrowid

@st.cache_data(ttl=60)
def get_tickets_for_user(_conn, user_id, is_analyst=False):
    base_query = """SELECT t.*, u1.full_name as created_by, u2.full_name as assigned_to
                    FROM tickets t
                    LEFT JOIN users u1 ON t.created_by_id = u1.id
                    LEFT JOIN users u2 ON t.assigned_to_id = u2.id"""
    if is_analyst:
        return pd.read_sql_query(f"{base_query} ORDER BY t.created_at DESC", _conn)
    else:
        return pd.read_sql_query(f"{base_query} WHERE t.created_by_id=? ORDER BY t.created_at DESC", _conn, params=(user_id,))

def update_ticket(conn, ticket_id, **kwargs):
    # Filtrer les clés dont la valeur est None pour éviter les erreurs
    valid_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    if not valid_kwargs:
        return # Ne rien faire si aucune donnée valide n'est fournie
    set_clause = ", ".join([f"{key} = ?" for key in valid_kwargs.keys()])
    sql = f'UPDATE tickets SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
    cur = conn.cursor()
    cur.execute(sql, list(valid_kwargs.values()) + [ticket_id])
    conn.commit()

def add_comment(conn, ticket_id, user_id, comment, is_internal=False):
    sql = 'INSERT INTO comments(ticket_id, user_id, comment, is_internal) VALUES(?,?,?,?)'
    cur = conn.cursor()
    cur.execute(sql, (ticket_id, user_id, comment, 1 if is_internal else 0))
    conn.commit()

@st.cache_data(ttl=30)
def get_comments(_conn, ticket_id):
    query = """SELECT c.*, u.full_name, u.username FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.ticket_id = ? ORDER BY c.created_at ASC"""
    return pd.read_sql_query(query, _conn, params=(ticket_id,))

@st.cache_data(ttl=120)
def get_dashboard_stats(_conn):
    stats = {}
    stats['total'] = pd.read_sql("SELECT COUNT(*) FROM tickets", _conn).iloc[0, 0]
    stats['new'] = pd.read_sql("SELECT COUNT(*) FROM tickets WHERE status = 'Nouveau'", _conn).iloc[0, 0]
    stats['in_progress'] = pd.read_sql("SELECT COUNT(*) FROM tickets WHERE status = 'En cours'", _conn).iloc[0, 0]
    stats['completed'] = pd.read_sql("SELECT COUNT(*) FROM tickets WHERE status = 'Terminé'", _conn).iloc[0, 0]
    stats['by_type'] = pd.read_sql("SELECT ticket_type, COUNT(*) as count FROM tickets GROUP BY ticket_type", _conn)
    stats['by_priority'] = pd.read_sql("SELECT priority, COUNT(*) as count FROM tickets GROUP BY priority", _conn)
    return stats

def get_ticket_count(conn):
    """Retourne le nombre total de tickets."""
    return pd.read_sql("SELECT COUNT(*) FROM tickets", conn).iloc[0, 0]


# ==============================================================================
# COMPOSANTS D'INTERFACE
# ==============================================================================

def show_auth_page():
    """Affiche la page de connexion ou d'inscription."""
    st.markdown(f'<div style="text-align: center;"><img src="{main_logo_url}" alt="Genève Aéroport Logo" width="250"></div>', unsafe_allow_html=True)

    st.markdown('<h1 style="text-align: center;">Portail de demandes</h1>', unsafe_allow_html=True)
    st.markdown('<h3 style="text-align: center; color: #B0B0C0;">Performance & Forecasting Operations</h3>', unsafe_allow_html=True)
    
    if 'auth_view' not in st.session_state: st.session_state.auth_view = 'login'

    _, center_col, _ = st.columns([1, 1.2, 1])

    if st.session_state.auth_view == 'login':
        with center_col:
            with st.form("login_form"):
                st.subheader("Connexion")
                username = st.text_input("Nom d'utilisateur", key="login_user")
                password = st.text_input("Mot de passe", type="password", key="login_pass")
                if st.form_submit_button("Se connecter", use_container_width=True, type="primary"):
                    conn = create_connection()
                    user = get_user(conn, username, password)
                    if user:
                        st.session_state.update({'logged_in': True, 'user_id': user[0], 'username': user[1], 'email': user[3], 'full_name': user[4], 'department': user[5], 'is_analyst': bool(user[6])})
                        st.rerun()
                    else:
                        st.error("Nom d'utilisateur ou mot de passe incorrect.")
            
            if st.button("Pas encore de compte ? Créez-en un.", use_container_width=True):
                st.session_state.auth_view = 'signup'; st.rerun()

    else: # signup view
        with center_col:
            with st.form("signup_form"):
                st.subheader("Créer un nouveau compte")
                new_full_name = st.text_input("Nom complet *")
                new_email = st.text_input("Email professionnel *")
                new_department = st.selectbox("Département *", [c.value for c in TicketCategory])
                st.markdown("---")
                new_username = st.text_input("Nom d'utilisateur *")
                new_password = st.text_input("Mot de passe *", type="password")
                
                if st.form_submit_button("S'inscrire", use_container_width=True, type="primary"):
                    if not all([new_username, new_password, new_email, new_full_name]):
                        st.warning("Veuillez remplir tous les champs obligatoires (*).")
                    else:
                        conn = create_connection()
                        user_id = add_user(conn, new_username, new_password, new_email, new_full_name, new_department)
                        if user_id:
                            st.toast(f"Compte pour {new_full_name} créé ! Redirection...", icon="✅")
                            time.sleep(2)
                            st.session_state.auth_view = 'login'
                            st.rerun()
                        else:
                            st.error("Ce nom d'utilisateur existe déjà.")
            
            if st.button("Déjà un compte ? Connectez-vous.", use_container_width=True):
                st.session_state.auth_view = 'login'; st.rerun()

def show_dashboard():
    """Affiche le dashboard avec les statistiques."""
    st.markdown("<h2><i class='bi bi-bar-chart-line-fill'></i> Tableau de bord global</h2>", unsafe_allow_html=True)
    conn = create_connection()
    stats = get_dashboard_stats(conn)
    
    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'><i class='bi bi-inbox-fill'></i> Total des demandes</div><div class='kpi-value'>{stats['total']}</div></div>", unsafe_allow_html=True)
    with kpi_cols[1]:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'><i class='bi bi-file-earmark-plus-fill'></i> Nouvelles demandes</div><div class='kpi-value'>{stats['new']}</div></div>", unsafe_allow_html=True)
    with kpi_cols[2]:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'><i class='bi bi-hourglass-split'></i> Demandes en cours</div><div class='kpi-value'>{stats['in_progress']}</div></div>", unsafe_allow_html=True)
    with kpi_cols[3]:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'><i class='bi bi-check-circle-fill'></i> Demandes terminées</div><div class='kpi-value'>{stats['completed']}</div></div>", unsafe_allow_html=True)

    
    st.markdown("---")
    
    chart_cols = st.columns(2)
    if not stats['by_type'].empty:
        fig_type = go.Figure(data=[go.Pie(labels=stats['by_type']['ticket_type'], values=stats['by_type']['count'], hole=.4)])
        fig_type.update_layout(title_text='Répartition par Type de Demande', showlegend=True, margin=dict(t=50, b=0, l=0, r=0))
        chart_cols[0].plotly_chart(fig_type, use_container_width=True)

    if not stats['by_priority'].empty:
        priority_order = [p.value for p in TicketPriority]
        stats['by_priority']['priority'] = pd.Categorical(stats['by_priority']['priority'], categories=priority_order, ordered=True)
        stats['by_priority'] = stats['by_priority'].sort_values('priority')
        
        fig_priority = px.bar(stats['by_priority'], x='priority', y='count', title="Volume par Priorité",
                              color='priority', text_auto=True,
                              color_discrete_map={'Critique': '#E74C3C', 'Élevée': '#F39C12', 'Normale': '#3498DB', 'Faible': '#2ECC71'})
        fig_priority.update_layout(xaxis_title="Priorité", yaxis_title="Nombre de demandes", showlegend=False)
        chart_cols[1].plotly_chart(fig_priority, use_container_width=True)

def show_ticket_form(ticket_to_edit=None):
    """Affiche le formulaire pour créer ou modifier un ticket."""
    is_edit_mode = ticket_to_edit is not None
    form_title = "Modifier la demande" if is_edit_mode else "Créer une nouvelle demande"
    button_label = "Enregistrer les modifications" if is_edit_mode else "Soumettre la demande"
    
    st.markdown(f"<h2><i class='bi bi-plus-square'></i> {form_title}</h2>", unsafe_allow_html=True)
    
    with st.form(key="ticket_form"):
        if not is_edit_mode:
            st.info("Veuillez fournir un maximum de détails pour une prise en charge efficace de votre demande.")
        
        title = st.text_input("Titre de la demande *", value=ticket_to_edit['title'] if is_edit_mode else "")
        
        col1, col2 = st.columns(2)
        type_options = [t.value for t in TicketType]
        priority_options = [p.value for p in TicketPriority]
        category_options = [c.value for c in TicketCategory]
        
        type_index = type_options.index(ticket_to_edit['ticket_type']) if is_edit_mode and ticket_to_edit['ticket_type'] in type_options else 0
        priority_index = priority_options.index(ticket_to_edit['priority']) if is_edit_mode and ticket_to_edit['priority'] in priority_options else 2
        category_index = category_options.index(ticket_to_edit['category']) if is_edit_mode and ticket_to_edit['category'] in category_options else 0
        delivery_date = pd.to_datetime(ticket_to_edit['expected_delivery']).date() if is_edit_mode and pd.notna(ticket_to_edit['expected_delivery']) else datetime.date.today()
        
        ticket_type = col1.selectbox("Type de demande *", type_options, index=type_index)
        priority = col2.selectbox("Niveau de priorité *", priority_options, index=priority_index)
        category = col1.selectbox("Catégorie fonctionnelle *", category_options, index=category_index)
        expected_delivery = col2.date_input("Date de livraison souhaitée", value=delivery_date, min_value=datetime.date.today())
        
        st.markdown("---")
        description = st.text_area("Description détaillée *", value=ticket_to_edit['description'] if is_edit_mode else "", height=150)
        business_justification = st.text_area("Justification métier *", value=ticket_to_edit['business_justification'] if is_edit_mode else "", height=100)
        
        with st.expander("Informations techniques (optionnel)"):
            data_sources = st.text_input("Sources de données", value=ticket_to_edit['data_sources'] if is_edit_mode else "")
            technical_requirements = st.text_area("Exigences techniques", value=ticket_to_edit['technical_requirements'] if is_edit_mode else "")
            estimated_hours = st.number_input("Estimation en heures", min_value=0, value=ticket_to_edit['estimated_hours'] if is_edit_mode and pd.notna(ticket_to_edit['estimated_hours']) else 0)

        if st.form_submit_button(button_label, use_container_width=True, type="primary"):
            if not all([title, description, business_justification]):
                st.error("Veuillez remplir tous les champs obligatoires (*).")
            else:
                conn = create_connection()
                if is_edit_mode:
                    update_payload = {
                        'title': title, 'description': description, 'ticket_type': ticket_type, 'category': category,
                        'priority': priority, 'business_justification': business_justification, 'expected_delivery': expected_delivery,
                        'data_sources': data_sources, 'technical_requirements': technical_requirements, 'estimated_hours': estimated_hours
                    }
                    update_ticket(conn, ticket_to_edit['id'], **update_payload)
                    st.toast("Demande modifiée avec succès !", icon="👍")
                else:
                    ticket_data = (title, description, ticket_type, category, priority, business_justification, expected_delivery, data_sources,
                                   technical_requirements, st.session_state['user_id'], estimated_hours if estimated_hours > 0 else None)
                    create_ticket(conn, ticket_data)
                    st.toast("Demande envoyée avec succès !", icon="🎉")
                    st.balloons()

                st.cache_data.clear()
                st.session_state.view = "Suivi des demandes"
                st.rerun()

def show_tickets_list():
    st.markdown("<h2><i class='bi bi-card-list'></i> Suivi des demandes</h2>", unsafe_allow_html=True)
    conn = create_connection()
    df = get_tickets_for_user(conn, st.session_state["user_id"], is_analyst=st.session_state["is_analyst"])
    analyst_list = get_all_analysts(conn)
    
    filter_cols = st.columns(4)
    status_filter = filter_cols[0].multiselect("Filtrer par statut", [s.value for s in TicketStatus])
    priority_filter = filter_cols[1].multiselect("Filtrer par priorité", [p.value for p in TicketPriority])
    search_query = filter_cols[2].text_input("Rechercher par titre...", placeholder="Titre de la demande...")
    
    if st.session_state["is_analyst"]:
        all_analysts = {analyst[0]: analyst[2] for analyst in analyst_list}
        all_analysts[None] = "Non assigné"
        assignee_filter = filter_cols[3].selectbox("Filtrer par analyste", options=list(all_analysts.keys()), format_func=lambda x: all_analysts.get(x, 'N/A'), index=None, placeholder="Choisir un analyste")
        if assignee_filter is not None:
            df = df[df['assigned_to_id'] == assignee_filter]

    if status_filter: df = df[df['status'].isin(status_filter)]
    if priority_filter: df = df[df['priority'].isin(priority_filter)]
    if search_query: df = df[df['title'].str.contains(search_query, case=False, na=False)]

    if df.empty:
        st.info("Aucune demande ne correspond à vos critères de recherche.")
        return

    for _, ticket in df.iterrows():
        
        expander_title = f"**#{ticket['id']} - {ticket['title']}**"
        
        with st.expander(expander_title, expanded=False):
            if ticket['status'] == 'Terminé':
                st.markdown('<div style="background-color:rgba(113, 128, 147, 0.1); padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">', unsafe_allow_html=True)

            priority_map = {"Critique": ("bi-exclamation-triangle-fill", "#E74C3C"), "Élevée": ("bi-exclamation-circle-fill", "#F39C12"), "Normale": ("bi-info-circle-fill", "#3498DB"), "Faible": ("bi-record-circle", "grey")}
            icon, color = priority_map.get(ticket['priority'], ("bi-question-circle", "white"))
            st.markdown(f"Statut : _{ticket['status']}_ | <span style='color:{color};'><i class='bi {icon}'></i> **Priorité :** {ticket['priority']}</span>", unsafe_allow_html=True)
            st.markdown("---")

            main_cols = st.columns([2, 1])
            with main_cols[0]:
                tab_details, tab_reqs, tab_analyst = st.tabs(["Détails", "Exigences", "Suivi Analyste"])
                with tab_details:
                    st.markdown(f"**Demandeur :** {ticket['created_by']} | **Date :** {pd.to_datetime(ticket['created_at']).strftime('%d/%m/%Y')}")
                    st.markdown(f"**Description:**\n> {ticket['description']}")
                    st.markdown(f"**Justification Métier:**\n> {ticket['business_justification']}")
                    
                    is_creator = st.session_state['user_id'] == ticket['created_by_id']
                    can_be_edited = ticket['status'] == 'Nouveau'
                    if is_creator and can_be_edited:
                        st.markdown("---")
                        if st.button("Modifier ma demande", key=f"edit_btn_{ticket['id']}", type="secondary"):
                            st.session_state.ticket_to_edit = ticket
                            st.session_state.view = "Modifier la demande"
                            st.rerun()

                with tab_reqs:
                    st.markdown(f"**Type:** {ticket['ticket_type']} | **Catégorie:** {ticket['category']}")
                    st.markdown(f"**Sources de données:** `{ticket['data_sources'] or 'N/A'}`")
                    st.markdown(f"**Exigences techniques:**\n> {ticket['technical_requirements'] or 'Aucune'}")
                with tab_analyst:
                    if st.session_state['is_analyst']:
                        with st.form(key=f"update_form_{ticket['id']}"):
                            form_cols = st.columns(3)
                            status_options = [s.value for s in TicketStatus]
                            new_status = form_cols[0].selectbox("Statut", status_options, index=status_options.index(ticket['status']))
                            
                            current_assignee = ticket['assigned_to_id']
                            assignee_ids = list(all_analysts.keys())
                            index = assignee_ids.index(current_assignee) if pd.notna(current_assignee) and current_assignee in assignee_ids else assignee_ids.index(None)
                            new_assignee_id = form_cols[1].selectbox("Assigné à", assignee_ids, format_func=lambda x: all_analysts.get(x, 'N/A'), index=index)
                            
                            actual_hours_value = ticket['actual_hours']
                            default_hours = int(actual_hours_value) if pd.notna(actual_hours_value) else 0
                            new_actual_hours = form_cols[2].number_input("Heures réelles", min_value=0, value=default_hours)
                            
                            if st.form_submit_button("Mettre à jour", type="primary"):
                                update_payload = {'status': new_status, 'assigned_to_id': new_assignee_id, 'actual_hours': new_actual_hours}
                                update_ticket(conn, ticket['id'], **update_payload)
                                st.toast(f"Ticket #{ticket['id']} mis à jour !", icon="👍"); time.sleep(1); st.cache_data.clear(); st.rerun()
                    else:
                        st.markdown(f"**Analyste assigné:** {ticket['assigned_to'] or 'Non assigné'}")
                        st.markdown(f"**Heures réelles:** {ticket['actual_hours'] or 'N/A'}")

            with main_cols[1]:
                st.subheader("Fil de discussion")
                comments_df = get_comments(conn, ticket['id'])
                for _, comment in comments_df.iterrows():
                    if comment['is_internal'] and not st.session_state['is_analyst']: continue
                    author = comment['full_name']
                    ts = pd.to_datetime(comment['created_at']).strftime('%d/%m %H:%M')
                    st.chat_message(name=author, avatar="🧑‍💻" if "OOP" in str(author) or "BI" in str(author) else "👤").write(f"*{ts}* - {comment['comment']}")
                
                with st.form(key=f"comment_form_{ticket['id']}", clear_on_submit=True):
                    new_comment = st.text_area("Ajouter un commentaire...", height=100, label_visibility="collapsed")
                    if st.form_submit_button("Envoyer", use_container_width=True):
                        if new_comment:
                            add_comment(conn, ticket['id'], st.session_state['user_id'], new_comment)
                            st.cache_data.clear(); st.rerun()

            if ticket['status'] == 'Terminé':
                st.markdown('</div>', unsafe_allow_html=True)


def show_user_management_page():
    """Affiche la page de gestion des utilisateurs pour les analystes."""
    st.markdown("<h2><i class='bi bi-people-fill'></i> Gestion des utilisateurs</h2>", unsafe_allow_html=True)
    conn = create_connection()
    
    if 'user_to_delete' in st.session_state and st.session_state.user_to_delete is not None:
        user_info = st.session_state.user_to_delete
        st.warning(f"Êtes-vous sûr de vouloir supprimer définitivement l'utilisateur **{user_info['full_name']}** ({user_info['username']}) ? Cette action est irréversible.")
        col1, col2 = st.columns(2)
        if col1.button("Oui, supprimer cet utilisateur", use_container_width=True, type="primary"):
            delete_user(conn, user_info['id'])
            st.toast(f"L'utilisateur {user_info['full_name']} a été supprimé.", icon="🗑️")
            st.session_state.user_to_delete = None
            st.rerun()
        if col2.button("Annuler", use_container_width=True):
            st.session_state.user_to_delete = None
            st.rerun()
        return

    users_df = get_all_users(conn)
    st.info("Modifiez les rôles des utilisateurs ou supprimez des comptes. Les administrateurs ne peuvent pas se supprimer eux-mêmes.")

    for index, user in users_df.iterrows():
        cols = st.columns([3, 2, 1])
        with cols[0]:
            st.markdown(f"**{user['full_name']}**")
            st.caption(f"_{user['email']}_ - {user['department']}")
        
        with cols[1]:
            is_self = user['id'] == st.session_state['user_id']
            new_role = st.toggle("Analyste OOP", value=bool(user['is_analyst']), key=f"role_{user['id']}", disabled=is_self)
            if new_role != bool(user['is_analyst']):
                update_user_role(conn, user['id'], new_role)
                st.toast(f"Rôle de {user['full_name']} mis à jour.", icon="🔄")
                st.rerun()
        
        with cols[2]:
            if st.button("Supprimer", key=f"delete_{user['id']}", disabled=is_self, use_container_width=True, type="secondary"):
                st.session_state.user_to_delete = user
                st.rerun()

def show_profile_page():
    st.markdown(f"<h2><i class='bi bi-person-circle'></i> Profil de {st.session_state['full_name']}</h2>", unsafe_allow_html=True)
    st.write(f"**Nom d'utilisateur :** {st.session_state['username']}")
    st.write(f"**Email :** {st.session_state['email']}")
    st.write(f"**Département :** {st.session_state['department']}")
    st.write(f"**Rôle :** {'Analyste OOP' if st.session_state['is_analyst'] else 'Utilisateur'}")

# ==============================================================================
# ROUTEUR PRINCIPAL
# ==============================================================================

def main():
    load_css()
    run_setup()
    
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    
    if st.session_state['logged_in']:
        
        with st.sidebar:
            st.title(f"Bonjour, {st.session_state.get('full_name', 'Utilisateur').split()[0]}")
            st.markdown("---")
            
            if "view" not in st.session_state:
                st.session_state.view = "Dashboard" if st.session_state.get('is_analyst') else "Suivi des demandes"

            if st.button("Suivi des demandes", use_container_width=True, type="primary" if st.session_state.view == "Suivi des demandes" else "secondary"):
                st.session_state.view = "Suivi des demandes"
            if st.button("Nouvelle demande", use_container_width=True, type="primary" if st.session_state.view == "Nouvelle demande" else "secondary"):
                st.session_state.view = "Nouvelle demande"
                
            if st.session_state.get('is_analyst'):
                st.markdown("---")
                st.subheader("Administration")
                if st.button("Dashboard", use_container_width=True, type="primary" if st.session_state.view == "Dashboard" else "secondary"):
                    st.session_state.view = "Dashboard"
                if st.button("Gestion des utilisateurs", use_container_width=True, type="primary" if st.session_state.view == "Gestion des utilisateurs" else "secondary"):
                    st.session_state.view = "Gestion des utilisateurs"
                
            st.markdown("---")
            if st.button("Mon Profil", use_container_width=True, type="primary" if st.session_state.view == "Mon Profil" else "secondary"):
                 st.session_state.view = "Mon Profil"
            if st.button("Déconnexion", use_container_width=True):
                auth_view = st.session_state.get('auth_view', 'login')
                for key in list(st.session_state.keys()): del st.session_state[key]
                st.session_state.auth_view = auth_view
                st.session_state.logged_in = False
                st.rerun()

        conn = create_connection()
        # --- Notification de nouveau ticket pour les analystes ---
        if st.session_state.get('is_analyst'):
            current_ticket_count = get_ticket_count(conn)
            if 'last_ticket_count' not in st.session_state:
                st.session_state.last_ticket_count = current_ticket_count
            
            if current_ticket_count > st.session_state.last_ticket_count:
                new_count = current_ticket_count - st.session_state.last_ticket_count
                plural = "s" if new_count > 1 else ""
                st.toast(f"{new_count} nouvelle{plural} demande{plural} !", icon="🔔")
                st.session_state.last_ticket_count = current_ticket_count
        
        if 'current_view' not in st.session_state: st.session_state.current_view = st.session_state.view
        if st.session_state.current_view != st.session_state.view:
            st.session_state.current_view = st.session_state.view
            st.rerun()
            
        if st.session_state.view == "Dashboard": show_dashboard()
        elif st.session_state.view == "Suivi des demandes": show_tickets_list()
        elif st.session_state.view == "Nouvelle demande": show_ticket_form()
        elif st.session_state.view == "Modifier la demande":
            if 'ticket_to_edit' in st.session_state:
                show_ticket_form(ticket_to_edit=st.session_state.ticket_to_edit)
            else:
                st.warning("Aucun ticket sélectionné pour la modification.")
                st.session_state.view = "Suivi des demandes"
                st.rerun()
        elif st.session_state.view == "Gestion des utilisateurs": show_user_management_page()
        elif st.session_state.view == "Mon Profil": show_profile_page()

    else:
        show_auth_page()

if __name__ == '__main__':
    main()
