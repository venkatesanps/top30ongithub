CREATE OR REPLACE PACKAGE BODY pkg_positions AS
  PROCEDURE refresh(p_date IN DATE) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
    TYPE t_ids IS TABLE OF stg_positions.position_id%TYPE;
    v_ids t_ids;
    v_cnt NUMBER;
  BEGIN
    SELECT position_id BULK COLLECT INTO v_ids FROM stg_positions WHERE as_of_date = p_date;
    FORALL i IN 1 .. v_ids.COUNT
      UPDATE positions SET refreshed = SYSDATE WHERE position_id = v_ids(i);
    DBMS_OUTPUT.PUT_LINE('rows: ' || SQL%ROWCOUNT);
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'POSITIONS');
    COMMIT;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RAISE_APPLICATION_ERROR(-20001, 'no positions for ' || p_date);
  END refresh;
END pkg_positions;
/
