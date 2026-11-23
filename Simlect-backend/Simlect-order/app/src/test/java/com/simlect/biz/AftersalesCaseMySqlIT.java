package com.simlect.biz;

/** Explicit opt-in integration suite. Not included by Surefire's default *Test pattern.
 * Reuses the exact service/controller/transaction/mapper assertions on MySQL.
 * Auth session remains an isolated fixture; order ownership uses the real order mapper.
 */
class AftersalesCaseMySqlIT extends AftersalesCasePersistenceTest {
    @Override protected boolean usesIsolatedMySql(){return true;}
    @org.junit.jupiter.api.Test void orderOwnershipIsReadFromActualSql(){
        org.junit.jupiter.api.Assertions.assertEquals("A",readFixtureOrder("O-A","A").getUserId());
        org.junit.jupiter.api.Assertions.assertNull(readFixtureOrder("O-B","A"));
        org.junit.jupiter.api.Assertions.assertEquals("B",readFixtureOrder("O-B","B").getUserId());
    }
}
