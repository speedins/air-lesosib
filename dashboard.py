import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
from datetime import datetime
import json

# Настройки страницы
st.set_page_config(
    page_title="Качество воздуха в Лесосибирске",
    page_icon="🌍",
    layout="wide"
)

# Заголовок
st.title("🌍 Качество атмосферного воздуха г. Лесосибирска")
st.markdown("Общедоступный мониторинг данных за 2022-2024 гг.")

# Ваш API ключ Яндекс.Карт
YANDEX_API_KEY = "c6d29f5d-142f-480b-a697-ce23ad183265"

# Функция загрузки данных
@st.cache_data(ttl=3600)
def load_data():
    try:
        engine = create_engine('mysql+pymysql://root:@localhost/lesosibirsk_air_monitoring')
        
        query = """
        SELECT 
            m.measurement_id,
            m.datetime,
            m.concentration,
            m.is_exceeded,
            s.name as station_name,
            s.latitude,
            s.longitude,
            s.type as station_type,
            p.name as pollutant_name,
            p.code as pollutant_code,
            p.pdk_max,
            p.unit
        FROM measurements m
        JOIN stations s ON m.station_id = s.station_id
        JOIN pollutants p ON m.pollutant_id = p.pollutant_id
        ORDER BY m.datetime DESC
        """
        
        df = pd.read_sql(query, engine)
        
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['year'] = df['datetime'].dt.year
            df['month'] = df['datetime'].dt.month
            df['date'] = df['datetime'].dt.date
            
        return df
        
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame()

# Загружаем данные
with st.spinner('Загрузка данных...'):
    df = load_data()

if df.empty:
    st.warning("Данные не загрузились. Проверьте подключение к БД.")
    st.stop()

# Сайдбар с фильтрами
st.sidebar.header("🔧 Фильтры")

# Фильтр по годам
years = sorted(df['year'].unique())
selected_years = st.sidebar.multiselect(
    "Выберите годы:",
    options=years,
    default=[2023, 2024] if 2023 in years and 2024 in years else years[:2]
)

# Фильтр по веществам
pollutants = sorted(df['pollutant_name'].unique())
selected_pollutants = st.sidebar.multiselect(
    "Выберите загрязняющие вещества:",
    options=pollutants,
    default=pollutants[:2] if len(pollutants) >= 2 else pollutants
)

# Фильтр по постам
stations = sorted(df['station_name'].unique())
selected_stations = st.sidebar.multiselect(
    "Выберите посты наблюдения:",
    options=stations,
    default=stations[:3] if len(stations) >= 3 else stations
)

# Применяем фильтры
filtered_df = df[
    (df['year'].isin(selected_years)) &
    (df['pollutant_name'].isin(selected_pollutants)) &
    (df['station_name'].isin(selected_stations))
]

# ========== РАЗДЕЛ 1: СТАТИСТИКА ==========
st.header("📊 Общая статистика")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Всего измерений", len(filtered_df))
with col2:
    st.metric("Постов наблюдения", filtered_df['station_name'].nunique())
with col3:
    st.metric("Загрязняющих веществ", filtered_df['pollutant_name'].nunique())
with col4:
    st.metric("Превышений ПДК", int(filtered_df['is_exceeded'].sum()))

# ========== РАЗДЕЛ 2: УЛУЧШЕННАЯ КАРТА С ЗОНАМИ ЗАГРЯЗНЕНИЯ ==========
st.header("🗺️ Карта загрязнения с зонами влияния")

if not filtered_df.empty:
    # Подготавливаем данные для карты
    map_data = filtered_df.groupby(['station_name', 'latitude', 'longitude']).agg({
        'concentration': 'mean',
        'is_exceeded': 'sum'
    }).reset_index()
    
    # Проверяем корректность координат
    map_data = map_data.dropna(subset=['latitude', 'longitude'])
    map_data['latitude'] = pd.to_numeric(map_data['latitude'], errors='coerce')
    map_data['longitude'] = pd.to_numeric(map_data['longitude'], errors='coerce')
    map_data = map_data.dropna(subset=['latitude', 'longitude'])
    
    if len(map_data) > 0:
        # Рассчитываем параметры
        max_conc = map_data['concentration'].max()
        min_conc = map_data['concentration'].min()
        center_lat = map_data['latitude'].mean()
        center_lon = map_data['longitude'].mean()
        
        # Создаем фигуру Plotly
        import plotly.graph_objects as go
        
        fig = go.Figure()
        
        # Добавляем зоны загрязнения (круги) ПЕРВЫМИ (чтобы были под метками)
        for idx, row in map_data.iterrows():
            concentration = row['concentration']
            exceedances = int(row['is_exceeded'])
            
            # Определяем цвет зоны
            if concentration > 0.06:
                zone_color = 'rgba(231, 76, 60, 0.15)'  # Красный, 15% прозрачность
                border_color = 'rgba(231, 76, 60, 0.7)'
            elif concentration > 0.03:
                zone_color = 'rgba(241, 196, 15, 0.15)'  # Желтый
                border_color = 'rgba(241, 196, 15, 0.7)'
            else:
                zone_color = 'rgba(46, 204, 113, 0.15)'  # Зеленый
                border_color = 'rgba(46, 204, 113, 0.7)'
            
            # Радиус зоны влияния (в метрах)
            zone_radius = 300 + (concentration * 10000)  # Базовый 300м + пропорционально концентрации
            zone_radius = min(zone_radius, 2000)  # Максимум 2км
            
            # Создаем круг (зона влияния)
            # Генерируем точки для круга
            import numpy as np
            
            # Координаты для круга
            t = np.linspace(0, 2*np.pi, 50)
            # Преобразуем метры в градусы (примерно: 1 градус ≈ 111км на широте 58°)
            radius_deg = zone_radius / 111000  # В градусах
            
            circle_lat = row['latitude'] + radius_deg * np.sin(t)
            circle_lon = row['longitude'] + radius_deg * np.cos(t) / np.cos(np.radians(row['latitude']))
            
            # Добавляем зону как многоугольник
            fig.add_trace(go.Scattermapbox(
                lat=list(circle_lat) + [circle_lat[0]],  # Замыкаем полигон
                lon=list(circle_lon) + [circle_lon[0]],
                mode='lines',
                fill='toself',
                fillcolor=zone_color,
                line=dict(color=border_color, width=2),
                hoverinfo='skip',
                showlegend=False,
                name=f"Зона влияния {row['station_name']}"
            ))
            
            # Внутренний круг (для градиентного эффекта)
            inner_radius_deg = radius_deg * 0.4
            inner_circle_lat = row['latitude'] + inner_radius_deg * np.sin(t)
            inner_circle_lon = row['longitude'] + inner_radius_deg * np.cos(t) / np.cos(np.radians(row['latitude']))
            
            fig.add_trace(go.Scattermapbox(
                lat=list(inner_circle_lat) + [inner_circle_lat[0]],
                lon=list(inner_circle_lon) + [inner_circle_lon[0]],
                mode='lines',
                fill='toself',
                fillcolor=zone_color.replace('0.15', '0.25'),  # Более насыщенный внутри
                line=dict(color=border_color, width=1),
                hoverinfo='skip',
                showlegend=False
            ))
        
        # Добавляем метки постов наблюдения ВТОРЫМИ (чтобы были поверх зон)
        for idx, row in map_data.iterrows():
            concentration = row['concentration']
            exceedances = int(row['is_exceeded'])
            
            # Определяем цвет и символ метки
            if concentration > 0.06:
                marker_color = '#e74c3c'  # Красный
                marker_symbol = 'circle'
                marker_size = 14
                level = '🔴 Высокий'
            elif concentration > 0.03:
                marker_color = '#f1c40f'  # Желтый
                marker_symbol = 'square'
                marker_size = 12
                level = '🟡 Средний'
            else:
                marker_color = '#2ecc71'  # Зеленый
                marker_symbol = 'triangle-up'
                marker_size = 10
                level = '🟢 Низкий'
            
            # Текст для всплывающей подсказки
            hover_text = f"""
            <b>📡 {row['station_name']}</b><br><br>
            <b>Концентрация:</b> {concentration:.3f} мг/м³<br>
            <b>Уровень:</b> {level}<br>
            <b>Превышений ПДК:</b> {exceedances}<br>
            <b>Зона влияния:</b> ~{int(300 + concentration * 10000)} м<br>
            <b>Координаты:</b> {row['latitude']:.5f}, {row['longitude']:.5f}
            """
            
            # Добавляем точку поста
            fig.add_trace(go.Scattermapbox(
                lat=[row['latitude']],
                lon=[row['longitude']],
                mode='markers+text',
                marker=dict(
                    size=marker_size,
                    color=marker_color,
                    symbol=marker_symbol,
                    opacity=0.9
                ),
                text=[f"{idx+1}"],  # Номер поста
                textposition="top center",
                textfont=dict(size=10, color='white', family='Arial Black'),
                hovertext=hover_text,
                hoverinfo='text',
                name=row['station_name'],
                showlegend=True
            ))
        
        # Настройки карты с включенным приближением
        fig.update_layout(
            mapbox=dict(
                style="open-street-map",  # Чистый стиль, хорошо видно зоны
                center=dict(lat=center_lat, lon=center_lon),
                zoom=11,
                # ВКЛЮЧАЕМ УПРАВЛЕНИЕ МАСШТАБОМ
                bearing=0,
                pitch=0,
                # Настройки контроллера карты
                layers=[
                    # Можно добавить дополнительные слои
                ],
                # Элементы управления
                uirevision='constant',  # Сохраняет состояние карты при обновлении
            ),
            margin=dict(l=0, r=0, t=30, b=0),
            height=600,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(255, 255, 255, 0.8)",
                bordercolor="rgba(0, 0, 0, 0.2)",
                borderwidth=1
            ),
            title=dict(
                text="Карта загрязнения с зонами влияния",
                x=0.5,
                xanchor="center"
            ),
            # Оптимизация для интерактивности
            dragmode='zoom',
            hovermode='closest',
        )
        
        # Дополнительные настройки для улучшения интерактивности
        fig.update_mapboxes(
            # Элементы управления на карте
            bearing=0,
            pitch=0,
            # Включаем все стандартные элементы управления Mapbox
            style="carto-positron",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=11,
            # Разрешаем все виды взаимодействий
            # (по умолчанию большинство из них уже включены)
        )
        
        # Добавляем шкалу загрязнения
        fig.add_trace(go.Scattermapbox(
            lat=[None],
            lon=[None],
            mode='markers',
            marker=dict(
                size=10,
                color='#2ecc71',
                symbol='triangle-up'
            ),
            name='🟢 Низкое (< 0.03 мг/м³)',
            showlegend=True
        ))
        
        fig.add_trace(go.Scattermapbox(
            lat=[None],
            lon=[None],
            mode='markers',
            marker=dict(
                size=12,
                color='#f1c40f',
                symbol='square'
            ),
            name='🟡 Среднее (0.03-0.06)',
            showlegend=True
        ))
        
        fig.add_trace(go.Scattermapbox(
            lat=[None],
            lon=[None],
            mode='markers',
            marker=dict(
                size=14,
                color='#e74c3c',
                symbol='circle'
            ),
            name='🔴 Высокое (> 0.06)',
            showlegend=True
        ))
        
        # ========== ИНФОРМАЦИЯ О УПРАВЛЕНИИ КАРТОЙ ==========
        st.markdown("""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
        <b>🗺️ Управление картой:</b>
        <ul style="margin: 5px 0; padding-left: 20px;">
            <li><b>Приближение:</b> Колесико мыши или двойной клик</li>
            <li><b>Отдаление:</b> Shift + колесико мыши или двойной клик правой кнопкой</li>
            <li><b>Перемещение:</b> Зажатая левая кнопка мыши + перемещение</li>
            <li><b>Вращение:</b> Ctrl + зажатая левая кнопка мыши + перемещение</li>
            <li><b>Наклон:</b> Ctrl + Shift + зажатая левая кнопка мыши + перемещение</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Отображаем карту
        st.plotly_chart(fig, use_container_width=True, config={
            'scrollZoom': True,  # Включаем приближение колесиком мыши
            'displayModeBar': True,  # Показываем панель инструментов
            'modeBarButtonsToAdd': ['zoomIn2d', 'zoomOut2d', 'resetScale2d'],
            'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
            'displaylogo': False,
        })
        
        # ========== ИНФОРМАЦИЯ ПОД КАРТОЙ ==========
        with st.expander("📖 Объяснение визуализации", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("""
                **🎯 Точки мониторинга:**
                - 🔺 Зеленый треугольник: низкое загрязнение
                - 🔶 Желтый квадрат: среднее загрязнение
                - 🔴 Красный круг: высокое загрязнение
                - Цифра: номер поста наблюдения
                """)
            
            with col2:
                st.markdown("""
                **🌫️ Зоны влияния:**
                - Светлые круги: предполагаемая зона распространения
                - Более насыщенный центр: эпицентр загрязнения
                - Размер круга: зависит от концентрации
                - Цвет зоны: соответствует уровню загрязнения
                """)
            
            with col3:
                st.markdown("""
                **📊 Уровни загрязнения:**
                - **Низкий:** < 0.03 мг/м³ (безопасно)
                - **Средний:** 0.03-0.06 мг/м³ (внимание)
                - **Высокий:** > 0.06 мг/м³ (опасно)
                """)
        
        # ========== ТАБЛИЦА С ДАННЫМИ ==========
        st.subheader("📋 Детальная информация по постам")
        
        # Создаем улучшенную таблицу
        display_data = map_data.copy()
        display_data['№'] = range(1, len(display_data) + 1)
        display_data['Концентрация'] = display_data['concentration'].apply(lambda x: f"{x:.3f} мг/м³")
        display_data['Превышения'] = display_data['is_exceeded'].astype(int)
        display_data['Уровень'] = display_data['concentration'].apply(
            lambda x: ('🔴 Высокий', '#ffebee') if x > 0.06 else 
                     ('🟡 Средний', '#fff3e0') if x > 0.03 else 
                     ('🟢 Низкий', '#e8f5e9')
        )
        
        # Разделяем на уровни для лучшего отображения
        display_data[['Уровень текст', 'Цвет фона']] = pd.DataFrame(display_data['Уровень'].tolist(), index=display_data.index)
        
        # Создаем стилизованную таблицу
        styled_table = display_data[['№', 'station_name', 'Концентрация', 'Превышения', 'Уровень текст']].copy()
        styled_table.columns = ['№', 'Пост наблюдения', 'Средняя концентрация', 'Превышений ПДК', 'Уровень загрязнения']
        
        # Отображаем с цветовым кодированием
        st.dataframe(
            styled_table.sort_values('Средняя концентрация', ascending=False),
            use_container_width=True,
            height=300,
            column_config={
                "Уровень загрязнения": st.column_config.TextColumn(
                    "Уровень",
                    help="Цветовое кодирование уровня загрязнения"
                )
            }
        )
        
        # ========== СТАТИСТИКА ==========
        st.subheader("📊 Статистика по карте")
        
        stat_cols = st.columns(4)
        with stat_cols[0]:
            avg_radius = (300 + map_data['concentration'].mean() * 10000)
            st.metric("Средний радиус зоны", f"{int(avg_radius)} м")
        
        with stat_cols[1]:
            max_conc = map_data['concentration'].max()
            max_radius = 300 + max_conc * 10000
            st.metric("Макс. радиус зоны", f"{int(min(max_radius, 2000))} м")
        
        with stat_cols[2]:
            high_pollution = len(map_data[map_data['concentration'] > 0.06])
            st.metric("Постов с высоким загрязнением", high_pollution)
        
        with stat_cols[3]:
            total_exceed = int(map_data['is_exceeded'].sum())
            st.metric("Всего превышений ПДК", total_exceed)
        
        # ========== ЭКСПОРТ ДАННЫХ КАРТЫ ==========
        st.download_button(
            label="📥 Скачать данные карты (CSV)",
            data=map_data.to_csv(index=False, encoding='utf-8'),
            file_name=f"map_data_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

else:
    st.warning("Нет данных для отображения карты. Измените параметры фильтров.")
# ========== РАЗДЕЛ 3: АНАЛИЗ ДАННЫХ ==========
st.header("📈 Анализ данных")

if not filtered_df.empty and selected_pollutants:
    # Создаем вкладки для разных типов анализа
    tab1, tab2, tab3 = st.tabs(["📊 Временные ряды", "📈 Сравнение по годам", "📋 Сравнение по постам"])
    
    with tab1:
        st.subheader("Динамика концентраций")
        
        # Выбор вещества для графика
        selected_pollutant = st.selectbox(
            "Выберите вещество для анализа:",
            selected_pollutants,
            key="pollutant_timeseries"
        )
        
        if selected_pollutant:
            # Фильтруем данные для выбранного вещества
            pollutant_data = filtered_df[filtered_df['pollutant_name'] == selected_pollutant]
            
            if not pollutant_data.empty:
                # Группируем по дате и посту
                time_data = pollutant_data.groupby(['date', 'station_name'])['concentration'].mean().reset_index()
                
                # Строим график
                fig = px.line(
                    time_data, 
                    x='date', 
                    y='concentration',
                    color='station_name',
                    title=f'Динамика концентраций {selected_pollutant}',
                    labels={'concentration': 'Концентрация, мг/м³', 'date': 'Дата'},
                    line_shape='spline'
                )
                
                # Добавляем линию ПДК если есть
                pdk_value = pollutant_data['pdk_max'].iloc[0]
                if pd.notna(pdk_value):
                    fig.add_hline(
                        y=pdk_value, 
                        line_dash="dash", 
                        line_color="red",
                        annotation_text=f"ПДК: {pdk_value} мг/м³",
                        annotation_position="bottom right"
                    )
                
                # Добавляем среднюю линию
                avg_value = time_data['concentration'].mean()
                fig.add_hline(
                    y=avg_value, 
                    line_dash="dot", 
                    line_color="blue",
                    annotation_text=f"Средняя: {avg_value:.3f} мг/м³",
                    annotation_position="top right"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Статистика по веществу
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Средняя концентрация", f"{avg_value:.3f} мг/м³")
                with col2:
                    max_conc = time_data['concentration'].max()
                    st.metric("Максимальная", f"{max_conc:.3f} мг/м³")
                with col3:
                    exceed_rate = (pollutant_data['is_exceeded'].sum() / len(pollutant_data)) * 100
                    st.metric("Процент превышений", f"{exceed_rate:.1f}%")
            else:
                st.warning("Нет данных для выбранного вещества")
    
    with tab2:
        st.subheader("Сравнение по годам")
        
        # Подготавливаем данные для сравнения
        yearly_comparison = filtered_df.groupby(['year', 'pollutant_name']).agg({
            'concentration': ['mean', 'max', 'count']
        }).reset_index()
        
        yearly_comparison.columns = ['year', 'pollutant_name', 'avg_concentration', 'max_concentration', 'measurements_count']
        
        if not yearly_comparison.empty:
            # График средних концентраций по годам
            fig = px.bar(
                yearly_comparison,
                x='year',
                y='avg_concentration',
                color='pollutant_name',
                title='Средние концентрации по годам',
                barmode='group',
                labels={'avg_concentration': 'Концентрация, мг/м³', 'year': 'Год'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Таблица сравнения
            st.write("**Детальное сравнение:**")
            st.dataframe(
                yearly_comparison.sort_values(['year', 'avg_concentration'], ascending=[True, False]),
                use_container_width=True
            )
    
    with tab3:
        st.subheader("Сравнение по постам наблюдения")
        
        # Подготавливаем данные для сравнения по постам
        station_comparison = filtered_df.groupby(['station_name', 'pollutant_name']).agg({
            'concentration': ['mean', 'max', 'count'],
            'is_exceeded': 'sum'
        }).reset_index()
        
        station_comparison.columns = ['station_name', 'pollutant_name', 'avg_concentration', 'max_concentration', 'measurements_count', 'exceedances']
        
        if not station_comparison.empty:
            # Heatmap сравнения
            pivot_data = station_comparison.pivot_table(
                index='station_name',
                columns='pollutant_name',
                values='avg_concentration',
                aggfunc='mean'
            ).fillna(0)
            
            fig = px.imshow(
                pivot_data,
                title='Тепловая карта концентраций по постам и веществам',
                labels=dict(x="Вещество", y="Пост", color="Концентрация, мг/м³"),
                aspect="auto",
                color_continuous_scale='RdYlGn_r'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Рейтинг постов по загрязнению
            st.write("**Рейтинг постов по уровню загрязнения:**")
            station_ranking = filtered_df.groupby('station_name')['concentration'].mean().sort_values(ascending=False)
            for idx, (station, conc) in enumerate(station_ranking.items(), 1):
                level = "🔴 Высокий" if conc > 0.06 else "🟡 Средний" if conc > 0.03 else "🟢 Низкий"
                st.write(f"{idx}. **{station}**: {conc:.3f} мг/м³ ({level})")

else:
    st.info("Выберите вещества и посты для анализа данных")

# ========== РАЗДЕЛ 4: ТАБЛИЦА ДАННЫХ ==========
st.header("📋 Последние измерения")

if not filtered_df.empty:
    # Показываем последние 15 записей
    display_df = filtered_df[['datetime', 'station_name', 'pollutant_name', 'concentration', 'unit', 'is_exceeded']].copy()
    display_df['Превышение'] = display_df['is_exceeded'].apply(lambda x: '✅ Да' if x == 1 else '❌ Нет')
    
    st.dataframe(
        display_df[['datetime', 'station_name', 'pollutant_name', 'concentration', 'unit', 'Превышение']]
        .sort_values('datetime', ascending=False)
        .head(15),
        use_container_width=True,
        height=400
    )
    
    # Кнопка экспорта
    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="📥 Скачать все данные в CSV",
        data=csv,
        file_name=f"lesosibirsk_air_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
else:
    st.info("Нет данных для отображения. Измените параметры фильтров.")

# ========== ИНФОРМАЦИЯ ==========
st.sidebar.header("📈 Статистика выборки")
if not filtered_df.empty:
    st.sidebar.write(f"**Выборка:** {len(filtered_df)} записей")
    st.sidebar.write(f"**Период:** {filtered_df['date'].min()} - {filtered_df['date'].max()}")
    
    # Топ-3 вещества по концентрации
    top_pollutants = filtered_df.groupby('pollutant_name')['concentration'].mean().nlargest(3)
    st.sidebar.write("**Топ-3 вещества:**")
    for pollutant, conc in top_pollutants.items():
        st.sidebar.write(f"- {pollutant.split('(')[0]}: {conc:.3f} мг/м³")

st.sidebar.header("ℹ️ О системе")
st.sidebar.info("""
**Источники данных:**
- Минэкологии Красноярского края
- Мониторинговая сеть
- Росгидромет

**Период:** 2022-2024 гг.

**Визуализация:**
- 🗺️ Карты: Яндекс.Карты
- 📈 Графики: Plotly
- 🎨 Дизайн: Streamlit

**Технологии:**
- Python + Streamlit
- MySQL база данных
- Яндекс.Карты API

**Контакты:**
ladys2151@gmail.com
""")

# Футер
st.markdown("---")
st.caption("""
Разработано для системы мониторинга качества атмосферного воздуха г. Лесосибирска • 2025
Используются Яндекс.Карты © Яндекс
""")