      *----------------------------------------------------------------*
      * PROGRAM:  ACCTPAY                                            *
      * PURPOSE:  ACCOUNTS PAYABLE BATCH PROCESSING                  *
      * FUNCTION: READS VENDOR/INVOICE FILES, APPLIES PAYMENTS,      *
      *           UPDATES DB TABLES AND WRITES PAYMENT OUTPUT FILE.  *
      *----------------------------------------------------------------*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTPAY.
       AUTHOR. ACCOUNTS-PAYABLE-SYSTEM.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-3090.
       OBJECT-COMPUTER. IBM-3090.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT VENDOR-FILE
               ASSIGN TO VENDMAST
               ORGANIZATION IS SEQUENTIAL.
           SELECT INVOICE-FILE
               ASSIGN TO INVOICES
               ORGANIZATION IS SEQUENTIAL.
           SELECT PAYMENT-FILE
               ASSIGN TO PAYMENTS
               ORGANIZATION IS SEQUENTIAL.
           SELECT REPORT-FILE
               ASSIGN TO RPTOUT
               ORGANIZATION IS SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD VENDOR-FILE
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 80 CHARACTERS.
       01 VENDOR-RECORD.
           05 VND-ID           PIC X(8).
           05 VND-NAME         PIC X(40).
           05 VND-BANK-ACCT    PIC X(16).
           05 FILLER           PIC X(16).

       FD INVOICE-FILE
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 120 CHARACTERS.
       01 INVOICE-RECORD.
           05 INV-NO           PIC X(10).
           05 INV-VND-ID       PIC X(8).
           05 INV-DATE         PIC X(8).
           05 INV-AMT          PIC S9(9)V99 COMP-3.
           05 INV-STATUS       PIC X(4).
           05 FILLER           PIC X(84).

       FD PAYMENT-FILE
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 80 CHARACTERS.
       01 PAYMENT-RECORD.
           05 PMT-DATE         PIC X(8).
           05 PMT-VND-ID       PIC X(8).
           05 PMT-AMT          PIC S9(9)V99 COMP-3.
           05 PMT-INV-NO       PIC X(10).
           05 FILLER           PIC X(46).

       FD REPORT-FILE
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 132 CHARACTERS.
       01 REPORT-RECORD        PIC X(132).

       WORKING-STORAGE SECTION.
       01 WS-COUNTERS.
           05 WS-INVOICE-COUNT PIC 9(6)    VALUE 0.
           05 WS-VENDOR-COUNT  PIC 9(6)    VALUE 0.
           05 WS-PAYMENT-COUNT PIC 9(6)    VALUE 0.
       01 WS-FLAGS.
           05 WS-EOF-FLAG      PIC X       VALUE 'N'.
           05 WS-ERROR-FLAG    PIC X       VALUE 'N'.
       01 WS-WORK-AREAS.
           05 WS-VND-ID        PIC X(8).
           05 WS-VND-NAME      PIC X(40).
           05 WS-VND-BANK      PIC X(16).
           05 WS-INV-NO        PIC X(10).
           05 WS-INV-AMT       PIC S9(9)V99 COMP-3.
           05 WS-INV-DATE      PIC X(8).
           05 WS-PMT-DATE      PIC X(8).
           05 WS-PMT-AMT       PIC S9(9)V99 COMP-3.
           05 WS-NET-AMT       PIC S9(9)V99 COMP-3.
           05 WS-DISCOUNT      PIC S9(5)V99 COMP-3.
           05 WS-WORK-DATE     PIC X(8).
       01 WS-ERROR-MSG         PIC X(80).
       01 WS-ERROR-CODE        PIC S9(4)    COMP.
       01 WS-DB-PARAMS.
           05 WS-DB-NAME       PIC X(8).
           05 WS-DB-USER       PIC X(8).
       01 WS-PAYMENT-AREA.
           05 WS-PMT-OUT-DATE  PIC X(8).
           05 WS-PMT-OUT-VND   PIC X(8).
           05 WS-PMT-OUT-AMT   PIC S9(9)V99 COMP-3.
           05 WS-PMT-OUT-INV   PIC X(10).
           05 FILLER           PIC X(46).

       LINKAGE SECTION.
       01 LS-PROCESS-PARAMS.
           05 LS-RUN-DATE      PIC X(8).
           05 LS-COMPANY-CODE  PIC X(4).
       01 LS-RETURN-CODE       PIC S9(4)    COMP.

       PROCEDURE DIVISION USING LS-PROCESS-PARAMS LS-RETURN-CODE.

       0000-MAIN-LOGIC.
           MOVE 0          TO WS-INVOICE-COUNT
           MOVE 0          TO WS-VENDOR-COUNT
           MOVE SPACES     TO WS-ERROR-MSG
           MOVE 'N'        TO WS-EOF-FLAG
           CALL 'DATEVAL'  USING LS-RUN-DATE WS-WORK-DATE
           CALL 'DBCONN'   USING WS-DB-PARAMS

           OPEN INPUT  VENDOR-FILE
           OPEN INPUT  INVOICE-FILE
           OPEN OUTPUT PAYMENT-FILE
           OPEN OUTPUT REPORT-FILE

       0100-PROCESS-VENDORS.
           READ VENDOR-FILE
               AT END
                   MOVE 'Y'    TO WS-EOF-FLAG
           END-READ
           IF WS-EOF-FLAG = 'Y'
               GO TO 0900-CLOSE-FILES
           END-IF
           MOVE VND-ID     TO WS-VND-ID
           ADD 1 TO WS-VENDOR-COUNT

       0200-LOOKUP-VENDOR.
           EXEC SQL
               SELECT VND_ID, VND_NAME, VND_BANK_ACCT
               INTO :WS-VND-ID, :WS-VND-NAME, :WS-VND-BANK
               FROM VENDOR_MASTER
               WHERE VND_ID = :WS-VND-ID
           END-EXEC

       0300-PROCESS-INVOICES.
           EXEC SQL
               SELECT INV_NO, INV_AMT, INV_DATE
               INTO :WS-INV-NO, :WS-INV-AMT, :WS-INV-DATE
               FROM INVOICE_HDR
               WHERE INV_VND_ID = :WS-VND-ID
               AND INV_STATUS = 'OPEN'
           END-EXEC

       0400-CALCULATE-PAYMENT.
           CALL 'CALCAMT' USING WS-INV-AMT WS-DISCOUNT WS-NET-AMT
           MOVE WS-NET-AMT TO WS-PMT-AMT
           MOVE WS-INV-NO  TO WS-PMT-OUT-INV

       0500-WRITE-PAYMENT.
           EXEC SQL
               INSERT INTO PAYMENT_AUDIT
                   (PMT_DATE, PMT_VND_ID, PMT_AMT, PMT_INV_NO)
               VALUES
                   (:WS-PMT-DATE, :WS-VND-ID,
                    :WS-PMT-AMT,  :WS-INV-NO)
           END-EXEC
           WRITE PAYMENT-RECORD FROM WS-PAYMENT-AREA
           ADD 1 TO WS-PAYMENT-COUNT

       0600-UPDATE-INVOICE.
           EXEC SQL
               UPDATE INVOICE_HDR
               SET INV_STATUS = 'PAID',
                   INV_PMT_DATE = :WS-PMT-DATE
               WHERE INV_NO = :WS-INV-NO
           END-EXEC

       0700-BROWSE-VENDORS.
           START VENDOR-FILE KEY = VND-ID

       0800-CLEANUP.
           EXEC SQL
               DELETE FROM TEMP_INVOICES
               WHERE PROC_DATE < :WS-WORK-DATE
           END-EXEC
           CALL 'ERRHANDL' USING WS-ERROR-CODE WS-ERROR-MSG
           ADD 1 TO WS-INVOICE-COUNT

       0900-CLOSE-FILES.
           CLOSE VENDOR-FILE
           CLOSE INVOICE-FILE
           CLOSE PAYMENT-FILE
           CLOSE REPORT-FILE
           MOVE 0 TO LS-RETURN-CODE
           STOP RUN.
