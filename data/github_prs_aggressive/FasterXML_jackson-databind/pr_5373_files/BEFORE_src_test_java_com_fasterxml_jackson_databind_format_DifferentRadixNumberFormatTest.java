package com.fasterxml.jackson.databind.format;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.testutil.DatabindTestUtil;
import org.junit.jupiter.api.Test;

import java.math.BigInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

public class DifferentRadixNumberFormatTest extends DatabindTestUtil {

    private static final String HEX_RADIX = "16";
    public static final String BINARY_RADIX = "2";

    private static class IntegerWrapper {
        public Integer value;

        public IntegerWrapper() {}
        public IntegerWrapper(Integer v) { value = v; }
    }

    private static class IntWrapper {
        public int value;

        public IntWrapper() {}
        public IntWrapper(int v) { value = v; }
    }

    private static class AnnotatedMethodIntWrapper {
        private int value;

        public AnnotatedMethodIntWrapper() {
        }
        public AnnotatedMethodIntWrapper(int v) {
            value = v;
        }

        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = HEX_RADIX)
        public int getValue() {
            return value;
        }
    }

    private static class IncorrectlyAnnotatedMethodIntWrapper {
        private int value;

        public IncorrectlyAnnotatedMethodIntWrapper() {
        }
        public IncorrectlyAnnotatedMethodIntWrapper(int v) {
            value = v;
        }

        @JsonFormat(shape = JsonFormat.Shape.STRING)
        public int getValue() {
            return value;
        }
    }

    private static class AllIntegralTypeWrapper {
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public byte byteValue;
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public Byte ByteValue;

        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public short shortValue;
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public Short ShortValue;

        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public int intValue;
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public Integer IntegerValue;

        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public long longValue;
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public Long LongValue;

        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = BINARY_RADIX)
        public BigInteger bigInteger;

        public AllIntegralTypeWrapper() {
        }

        public AllIntegralTypeWrapper(byte byteValue, Byte ByteValue, short shortValue, Short ShortValue, int intValue,
                                      Integer IntegerValue, long longValue, Long LongValue, BigInteger bigInteger) {
            this.byteValue = byteValue;
            this.ByteValue = ByteValue;
            this.shortValue = shortValue;
            this.ShortValue = ShortValue;
            this.intValue = intValue;
            this.IntegerValue = IntegerValue;
            this.longValue = longValue;
            this.LongValue = LongValue;
            this.bigInteger = bigInteger;
        }
    }

    @Test
    void testIntegerSerializedAsHexString()
            throws JsonProcessingException {
        ObjectMapper mapper = newJsonMapper();
        mapper.configOverride(Integer.class).setFormat(JsonFormat.Value.forShape(JsonFormat.Shape.STRING).withPattern(HEX_RADIX));
        IntegerWrapper initialIntegerWrapper = new IntegerWrapper(10);
        String json = mapper.writeValueAsString(initialIntegerWrapper);
        String expectedJson = "{'value':'a'}";

        assertEquals(a2q(expectedJson), json);

        IntegerWrapper readBackIntegerWrapper = mapper.readValue(a2q(expectedJson), IntegerWrapper.class);

        assertNotNull(readBackIntegerWrapper);
        assertEquals(initialIntegerWrapper.value, readBackIntegerWrapper.value);
    }


    @Test
    void testIntSerializedAsHexString()
            throws JsonProcessingException {
        ObjectMapper mapper = newJsonMapper();
        mapper.configOverride(int.class)
              .setFormat(JsonFormat.Value.forShape(JsonFormat.Shape.STRING).withPattern(HEX_RADIX));
        IntWrapper intialIntWrapper = new IntWrapper(10);
        String expectedJson = "{'value':'a'}";

        String json = mapper.writeValueAsString(intialIntWrapper);

        assertEquals(a2q(expectedJson), json);

        IntWrapper readBackIntWrapper = mapper.readValue(a2q(expectedJson), IntWrapper.class);

        assertNotNull(readBackIntWrapper);
        assertEquals(intialIntWrapper.value, readBackIntWrapper.value);

    }

    @Test
    void testAnnotatedAccessorSerializedAsHexString()
            throws JsonProcessingException {
        ObjectMapper mapper = newJsonMapper();
        AnnotatedMethodIntWrapper initialIntWrapper = new AnnotatedMethodIntWrapper(10);
        String expectedJson = "{'value':'a'}";

        String json = mapper.writeValueAsString(initialIntWrapper);

        assertEquals(a2q(expectedJson), json);

        AnnotatedMethodIntWrapper readBackIntWrapper = mapper.readValue(a2q(expectedJson), AnnotatedMethodIntWrapper.class);

        assertNotNull(readBackIntWrapper);
        assertEquals(initialIntWrapper.value, readBackIntWrapper.value);
    }

    @Test
    void testAnnotatedAccessorWithoutPatternDoesNotThrow()
            throws JsonProcessingException {
        ObjectMapper mapper = newJsonMapper();
        IncorrectlyAnnotatedMethodIntWrapper initialIntWrapper = new IncorrectlyAnnotatedMethodIntWrapper(10);
        String expectedJson = "{'value':'10'}";

        String json = mapper.writeValueAsString(initialIntWrapper);

        assertEquals(a2q(expectedJson), json);
    }

    @Test
    void testUsingDefaultConfigOverrideRadixToSerializeAsHexString()
            throws JsonProcessingException {
        ObjectMapper mapper = newJsonMapper();
        mapper.configOverride(Integer.class)
              .setFormat(JsonFormat.Value.forShape(JsonFormat.Shape.STRING));
        mapper.setDefaultFormat(HEX_RADIX);
        IntegerWrapper intialIntegerWrapper = new IntegerWrapper(10);
        String expectedJson = "{'value':'a'}";

        String json = mapper.writeValueAsString(intialIntegerWrapper);

        assertEquals(a2q(expectedJson), json);

        IntegerWrapper readBackIntegerWrapper = mapper.readValue(a2q(expectedJson), IntegerWrapper.class);

        assertNotNull(readBackIntegerWrapper);
        assertEquals(intialIntegerWrapper.value, readBackIntegerWrapper.value);
    }

    @Test
    void testAllIntegralTypesGetSerializedAsBinary()
            throws JsonProcessingException {
        ObjectMapper mapper = newJsonMapper();
        AllIntegralTypeWrapper initialIntegralTypeWrapper = new AllIntegralTypeWrapper((byte) 1,
                (byte) 2, (short) 3, (short) 4, 5, 6, 7L, 8L, new BigInteger("9"));
        String expectedJson = "{'byteValue':'1','ByteValue':'10','shortValue':'11','ShortValue':'100','intValue':'101','IntegerValue':'110','longValue':'111','LongValue':'1000','bigInteger':'1001'}";

        String json = mapper.writeValueAsString(initialIntegralTypeWrapper);

        assertEquals(a2q(expectedJson), json);

        AllIntegralTypeWrapper readbackIntegralTypeWrapper = mapper.readValue(a2q(expectedJson), AllIntegralTypeWrapper.class);

        assertNotNull(readbackIntegralTypeWrapper);
        assertEquals(initialIntegralTypeWrapper.byteValue, readbackIntegralTypeWrapper.byteValue);
        assertEquals(initialIntegralTypeWrapper.ByteValue, readbackIntegralTypeWrapper.ByteValue);
        assertEquals(initialIntegralTypeWrapper.shortValue, readbackIntegralTypeWrapper.shortValue);
        assertEquals(initialIntegralTypeWrapper.ShortValue, readbackIntegralTypeWrapper.ShortValue);
        assertEquals(initialIntegralTypeWrapper.intValue, readbackIntegralTypeWrapper.intValue);
        assertEquals(initialIntegralTypeWrapper.IntegerValue, readbackIntegralTypeWrapper.IntegerValue);
        assertEquals(initialIntegralTypeWrapper.longValue, readbackIntegralTypeWrapper.longValue);
        assertEquals(initialIntegralTypeWrapper.LongValue, readbackIntegralTypeWrapper.LongValue);
        assertEquals(initialIntegralTypeWrapper.bigInteger, readbackIntegralTypeWrapper.bigInteger);
    }
}
