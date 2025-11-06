"""
Page Simulateur Objectif - Simulation d'objectifs de coût
"""
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

from models.suggestion import AjustementPropose


def render_simulateur_objectif_page():
    """Affiche la page Simulateur Objectif"""
    st.title("Simulateur d'Objectif de Coût")
    st.markdown(
        "Simulez l'impact en heures d'un ajustement de coût global (augmentation/réduction) "
        "en le répartissant sur les catégories."
    )

    # Pré-requis : Budget généré
    bs = st.session_state.get('budget_state', {})
    if not bs or 'year' not in bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
        st.warning(
            "⚠️ Aucun budget annuel valide en mémoire. "
            "Veuillez d'abord en générer un via la page **Budget Annuel**."
        )
        st.stop()

    # Logique du Simulateur
    with st.container(border=True):
        st.subheader("Simulation d'Objectif de Coût Annuel")
        st.markdown(
            "Répartissez un objectif de coût global (augmentation/réduction) entre les "
            "catégories pour voir l'impact en heures. *Cet outil est un simulateur et "
            "n'applique pas de règles.*"
        )

        # 1. Récupérer les données de base
        base_cost_planif = bs.get('totals', {}).get('cout_annuel', 0.0)
        cost_mapping = st.session_state.get('cost_mapping', {})
        personnel_df = st.session_state.get('personnel', pd.DataFrame())
        all_categories = sorted(list(st.session_state.get('perimetres', {}).keys()))

        # Calculer les coûts de formation (même logique que Budget Annuel, Besoin Jour et Analyse Budgétaire)
        total_cout_formation = 0.0
        cout_horaire_at = 45.50
        if 'personnel' in st.session_state and not st.session_state.personnel.empty:
            at_row = st.session_state.personnel[st.session_state.personnel['Type'] == 'AT']
            if not at_row.empty:
                try:
                    cout_horaire_at = float(at_row['Coût Horaire'].iloc[0])
                except Exception:
                    pass
        if 'budget_formation_at' in st.session_state:
            df_formation = st.session_state.budget_formation_at.copy()
            df_formation['Effectif (pers.)'] = pd.to_numeric(df_formation.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
            df_formation['Heures'] = df_formation.get('Heures', 0).apply(lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0).clip(lower=0)
            df_formation['Nbre de shifts'] = pd.to_numeric(df_formation.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
            df_formation['Total (heures)'] = (
                df_formation['Effectif (pers.)'] *
                df_formation['Heures'] *
                df_formation['Nbre de shifts']
            )
            total_heures_formation = df_formation['Total (heures)'].sum()
            total_cout_formation = total_heures_formation * cout_horaire_at

        # Calculer les coûts des formateurs (ATF)
        total_cout_formateurs = 0.0
        cout_horaire_atf = 52.00
        if 'personnel' in st.session_state and not st.session_state.personnel.empty:
            atf_row = st.session_state.personnel[st.session_state.personnel['Type'] == 'ATF']
            if not atf_row.empty:
                try:
                    cout_horaire_atf = float(atf_row['Coût Horaire'].iloc[0])
                except Exception:
                    pass
        if 'budget_formateurs_at' in st.session_state:
            df_formateurs = st.session_state.budget_formateurs_at.copy()
            df_formateurs['Effectif (pers.)'] = pd.to_numeric(df_formateurs.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
            df_formateurs['Heures'] = df_formateurs.get('Heures', 0).apply(lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0).clip(lower=0)
            df_formateurs['Nbre de shifts'] = pd.to_numeric(df_formateurs.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
            df_formateurs['Total (heures)'] = (
                df_formateurs['Effectif (pers.)'] *
                df_formateurs['Heures'] *
                df_formateurs['Nbre de shifts']
            )
            total_heures_formateurs = df_formateurs['Total (heures)'].sum()
            total_cout_formateurs = total_heures_formateurs * cout_horaire_atf

        # Total avec formation (cohérent avec Budget Annuel, Besoin Jour et Analyse Budgétaire)
        base_cost_total = base_cost_planif + total_cout_formation + total_cout_formateurs

        st.metric("Budget Annuel de Base (avec formation)", f"{base_cost_total:,.0f} CHF")

        # 2. Construire le mapping des tarifs horaires
        category_hourly_rates = {}
        missing_rates = []
        if personnel_df.empty:
            st.error("Définissez les tarifs du personnel dans la 'Configuration'.")
        else:
            for cat in all_categories:
                personnel_type = cost_mapping.get(cat)
                if personnel_type:
                    rate_row = personnel_df[personnel_df['Type'] == personnel_type]
                    if not rate_row.empty:
                        try:
                            rate = float(rate_row['Coût Horaire'].iloc[0])
                            if rate > 0:
                                category_hourly_rates[cat] = rate
                            else:
                                category_hourly_rates[cat] = 0.0
                                missing_rates.append(f"'{cat}' (tarif à 0)")
                        except Exception:
                            category_hourly_rates[cat] = 0.0
                            missing_rates.append(f"'{cat}' (tarif invalide)")
                    else:
                        category_hourly_rates[cat] = 0.0
                        missing_rates.append(f"'{cat}' (type '{personnel_type}' non trouvé)")
                else:
                    category_hourly_rates[cat] = 0.0
                    missing_rates.append(f"'{cat}' (pas de mapping)")

        if missing_rates:
            st.warning(
                f"Calcul impossible pour : {', '.join(missing_rates)}. "
                "Vérifiez 'Configuration' et 'Association des Coûts'."
            )

        st.divider()

        # 3. Inputs utilisateur
        target_adjustment = st.number_input(
            "Objectif d'ajustement (en CHF, négatif pour réduire)",
            value=0.0,
            step=1000.0,
            format="%.0f",
            key="sim_target_adjustment"
        )

        st.markdown("**Répartition de l'ajustement (%) :**")

        # Layout avec colonnes
        num_categories = len(all_categories)
        cols_per_row = 5
        num_rows = (num_categories + cols_per_row - 1) // cols_per_row

        distrib_pct = {}
        total_pct = 0.0

        cat_iter = iter(all_categories)
        for _ in range(num_rows):
            cols = st.columns(cols_per_row)
            for i in range(cols_per_row):
                try:
                    cat = next(cat_iter)
                    with cols[i]:
                        # Initialiser à 0 si pas dans l'état
                        if f'distrib_pct_{cat}' not in st.session_state:
                            st.session_state[f'distrib_pct_{cat}'] = 0.0

                        # Ne pas utiliser value= quand on utilise key= avec session_state
                        pct = st.number_input(
                            f"% {cat}",
                            min_value=0.0,
                            max_value=100.0,
                            step=1.0,
                            key=f'distrib_pct_{cat}',
                            format="%.1f"
                        )
                        distrib_pct[cat] = pct
                        total_pct += pct
                except StopIteration:
                    pass

        # Afficher le total des pourcentages
        if abs(total_pct - 100.0) > 0.1:
            st.warning(
                f"Le total des pourcentages est de **{total_pct:.1f}%**. "
                "Il devrait être de 100%."
            )
        else:
            st.success(f"Total des pourcentages : {total_pct:.1f}%.")

        st.divider()

        # 4. Calcul et affichage
        if target_adjustment != 0:
            if abs(total_pct) < 0.1:
                st.error(
                    "Veuillez définir une répartition (pourcentage) pour au moins "
                    "une catégorie."
                )
            else:
                results = []
                for cat in all_categories:
                    # Normaliser la répartition si le total n'est pas 100%
                    pct_of_target = (distrib_pct.get(cat, 0.0) / total_pct) \
                                    if total_pct > 0 else 0.0

                    cost_adjustment_cat_raw = target_adjustment * pct_of_target
                    cost_adjustment_cat = np.ceil(cost_adjustment_cat_raw)

                    hourly_rate = category_hourly_rates.get(cat, 0.0)

                    hour_adjustment_cat = 0.0
                    if hourly_rate > 0:
                        # Utilise le coût non arrondi pour un calcul d'heures plus précis
                        hour_adjustment_cat_raw = cost_adjustment_cat_raw / hourly_rate
                        hour_adjustment_cat = np.ceil(hour_adjustment_cat_raw)
                    elif cost_adjustment_cat != 0:
                        hour_adjustment_cat = 999999.0  # Valeur indiquant l'impossibilité

                    results.append({
                        'Catégorie': cat,
                        'Part Répartition (%)': distrib_pct.get(cat, 0.0),
                        'Ajustement Coût (CHF)': cost_adjustment_cat,
                        'Tarif Horaire (CHF)': hourly_rate,
                        'Ajustement Heures (h)': hour_adjustment_cat
                    })

                results_df = pd.DataFrame(results)
                # Filtrer les lignes avec 0% de distribution
                results_df = results_df[results_df['Part Répartition (%)'] > 0].copy()

                st.subheader("Résultat de la Simulation")
                # Avertissement si le total n'est pas 100%
                if abs(total_pct - 100.0) > 0.1:
                    st.info(
                        f"Note : Les montants ont été ajustés proportionnellement car le total "
                        f"de la répartition est de {total_pct:.1f}%."
                    )

                st.dataframe(
                    results_df,
                    column_config={
                        'Part Répartition (%)': st.column_config.NumberColumn(format="%.1f%%"),
                        'Ajustement Coût (CHF)': st.column_config.NumberColumn(
                            format="%.0f"
                        ),
                        'Tarif Horaire (CHF)': st.column_config.NumberColumn(format="%.2f"),
                        'Ajustement Heures (h)': st.column_config.NumberColumn(
                            format="%.0f"
                        ),
                    },
                    hide_index=True,
                    use_container_width=True
                )

                st.divider()

                # Bouton pour envoyer vers Assistant Besoin Jour
                st.subheader("🤖 Assistant Besoin Jour")
                st.markdown(
                    "Envoyez cet ajustement à l'**Assistant Besoin Jour** pour obtenir "
                    "des suggestions automatiques basées sur les données PAX et votre planning."
                )

                col1, col2 = st.columns([3, 1])
                with col1:
                    # Options de verrous (optionnel)
                    with st.expander("⚙️ Options Avancées (Verrous)"):
                        st.markdown(
                            "Les verrous empêchent l'assistant de modifier certains "
                            "périmètres ou dates spécifiques."
                        )
                        locked_perimetres = st.multiselect(
                            "Verrouiller des périmètres (AT)",
                            options=st.session_state.perimetres.get("AT", []),
                            default=[],
                            key="locked_perimetres"
                        )
                        # TODO V2: Ajouter sélection de dates verrouillées

                with col2:
                    if st.button(
                        "📤 Envoyer vers Assistant",
                        type="primary",
                        use_container_width=True,
                        key="send_to_assistant_btn"
                    ):
                        # Créer l'objet AjustementPropose
                        distribution = {}
                        for _, row in results_df.iterrows():
                            cat = row['Catégorie']
                            distribution[cat] = {
                                'delta_hours': float(row['Ajustement Heures (h)']),
                                'delta_chf': float(row['Ajustement Coût (CHF)']),
                                'percentage': float(row['Part Répartition (%)'])
                            }

                        ajustement = AjustementPropose(
                            total_delta_hours=float(results_df['Ajustement Heures (h)'].sum()),
                            total_delta_chf=float(target_adjustment),
                            distribution=distribution,
                            locks={
                                'categories': [],  # Pas de verrous catégories dans V1
                                'perimetres': locked_perimetres if 'locked_perimetres' in locals() else [],
                                'dates': []  # TODO V2
                            },
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )

                        # Stocker dans session_state
                        st.session_state.ajustement_propose = ajustement

                        st.success(
                            "✅ Ajustement envoyé à l'Assistant Besoin Jour ! "
                            "Rendez-vous sur la page **Assistant Besoin Jour** pour générer les suggestions."
                        )
                        st.balloons()

        else:
            st.info("Saisissez un objectif d'ajustement non nul pour lancer la simulation.")
