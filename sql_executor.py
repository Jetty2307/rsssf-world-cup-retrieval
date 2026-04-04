from ingest import get_connection


def execute_sql_route(question, route):
    operation = select_operation(question, route)
    sql, params = build_sql(operation, route)

    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    answer = format_result(operation, rows, route)
    return {
        "operation": operation,
        "sql": sql,
        "params": params,
        "rows": rows,
        "answer": answer,
    }


def select_operation(question, route):
    target_table = route.get("target_table")
    lowered = question.lower()

    if target_table == "squads":
        if route.get("shirt_number") is not None:
            return "person_by_shirt_number"
        if "coach" in lowered:
            return "coach_by_team_year"
        if route.get("person"):
            return "person_lookup_in_squad"
        return "squad_by_team_year"

    if target_table == "competition_results":
        time_relation = (route.get("time_relation") or "").lower()
        if time_relation in {"last", "latest"}:
            return "latest_competition_year"
        if time_relation in {"first", "earliest"}:
            return "earliest_competition_year"
        if route.get("start_year") is not None or route.get("end_year") is not None:
            return "results_between_years"
        if "runner-up" in lowered or "runner up" in lowered:
            return "runner_up_by_year"
        return "winner_by_year"

    raise ValueError(f"SQL execution is not supported for target_table={target_table!r}")


def build_sql(operation, route):
    competition = route.get("competition") or "World Cup"
    year = route.get("year")
    team = route.get("team")
    person = route.get("person")
    shirt_number = route.get("shirt_number")
    start_year = route.get("start_year")
    end_year = route.get("end_year")

    if operation == "squad_by_team_year":
        require_fields(route, "team", "year")
        return (
            """
            select person_name, role, shirt_number, club
            from squads
            where team ilike %s and year = %s
            order by
                case when role = 'coach' then 1 else 0 end,
                shirt_number nulls last,
                person_name
            """,
            [f"%{team}%", year],
        )

    if operation == "person_by_shirt_number":
        require_fields(route, "team", "year", "shirt_number")
        return (
            """
            select person_name, role, club
            from squads
            where team ilike %s and year = %s and shirt_number = %s
            order by person_name
            """,
            [f"%{team}%", year, shirt_number],
        )

    if operation == "coach_by_team_year":
        require_fields(route, "team", "year")
        return (
            """
            select person_name, club
            from squads
            where team ilike %s and year = %s and role = 'coach'
            order by person_name
            """,
            [f"%{team}%", year],
        )

    if operation == "person_lookup_in_squad":
        require_fields(route, "team", "year", "person")
        return (
            """
            select person_name, role, shirt_number, club
            from squads
            where team ilike %s and year = %s and person_name ilike %s
            order by person_name
            """,
            [f"%{team}%", year, f"%{person}%"],
        )

    if operation == "winner_by_year":
        require_fields(route, "year")
        return (
            """
            select competition, year, winner
            from competition_results
            where competition ilike %s and year = %s
            order by year
            limit 1
            """,
            [f"%{competition}%", year],
        )

    if operation == "runner_up_by_year":
        require_fields(route, "year")
        return (
            """
            select competition, year, runner_up
            from competition_results
            where competition ilike %s and year = %s
            order by year
            limit 1
            """,
            [f"%{competition}%", year],
        )

    if operation == "latest_competition_year":
        return (
            """
            select competition, year, winner
            from competition_results
            where competition ilike %s and year is not null
            order by year desc
            limit 1
            """,
            [f"%{competition}%"],
        )

    if operation == "earliest_competition_year":
        return (
            """
            select competition, year, winner
            from competition_results
            where competition ilike %s and year is not null
            order by year asc
            limit 1
            """,
            [f"%{competition}%"],
        )

    if operation == "results_between_years":
        clauses = ["competition ilike %s", "year is not null"]
        params = [f"%{competition}%"]
        if start_year is not None:
            clauses.append("year >= %s")
            params.append(start_year)
        if end_year is not None:
            clauses.append("year <= %s")
            params.append(end_year)

        return (
            f"""
            select competition, year, winner, runner_up
            from competition_results
            where {' and '.join(clauses)}
            order by year
            """,
            params,
        )

    raise ValueError(f"Unsupported SQL operation: {operation}")


def format_result(operation, rows, route):
    if not rows:
        return "No matching rows found."

    if operation == "squad_by_team_year":
        team = route["team"]
        year = route["year"]
        people = []
        for person_name, role, shirt_number, club in rows:
            label = person_name
            if role == "coach":
                label += " (coach)"
            elif shirt_number is not None:
                label += f" (#{shirt_number})"
            if club:
                label += f" - {club}"
            people.append(label)
        return f"{team} {year} squad: " + "; ".join(people)

    if operation == "person_by_shirt_number":
        person_name, role, club = rows[0]
        extra = f", {club}" if club else ""
        return f"{person_name} was listed as {role}{extra}."

    if operation == "coach_by_team_year":
        coaches = [row[0] for row in rows]
        return "Coach: " + ", ".join(coaches)

    if operation == "person_lookup_in_squad":
        person_name, role, shirt_number, club = rows[0]
        details = [role]
        if shirt_number is not None:
            details.append(f"shirt number {shirt_number}")
        if club:
            details.append(club)
        return f"{person_name}: " + ", ".join(details)

    if operation == "winner_by_year":
        competition, year, winner = rows[0]
        if winner:
            return f"{winner} won the {competition} in {year}."
        return f"No winner is recorded for the {competition} in {year}."

    if operation == "runner_up_by_year":
        competition, year, runner_up = rows[0]
        if runner_up:
            return f"{runner_up} were the runner-up in the {competition} in {year}."
        return f"No runner-up is recorded for the {competition} in {year}."

    if operation == "latest_competition_year":
        competition, year, winner = rows[0]
        if winner:
            return f"The latest recorded {competition} was in {year}, won by {winner}."
        return f"The latest recorded {competition} was in {year}."

    if operation == "earliest_competition_year":
        competition, year, winner = rows[0]
        if winner:
            return f"The earliest recorded {competition} was in {year}, won by {winner}."
        return f"The earliest recorded {competition} was in {year}."

    if operation == "results_between_years":
        parts = []
        for competition, year, winner, runner_up in rows:
            item = f"{year}: {winner or 'unknown winner'}"
            if runner_up:
                item += f" vs {runner_up}"
            parts.append(item)
        return "; ".join(parts)

    raise ValueError(f"No formatter implemented for operation: {operation}")


def require_fields(route, *fields):
    missing = [field for field in fields if route.get(field) is None]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Missing required route fields: {names}")
