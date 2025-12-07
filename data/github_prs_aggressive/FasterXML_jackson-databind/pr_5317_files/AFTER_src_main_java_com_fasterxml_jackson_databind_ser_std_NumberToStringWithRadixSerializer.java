package com.fasterxml.jackson.databind.ser.std;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.annotation.JacksonStdImpl;

import java.io.IOException;
import java.math.BigInteger;

/**
 * Serializer used to convert numbers into a representation for a specified radix (base) and serialize
 * the representation as string.
 *
 * @since 2.21
 */
@JacksonStdImpl
public class NumberToStringWithRadixSerializer extends ToStringSerializerBase {
    private final int radix;

    public NumberToStringWithRadixSerializer(int radix) { super(Object.class);
        this.radix = radix;
    }

    public NumberToStringWithRadixSerializer(Class<?> handledType, int radix) {
        super(handledType);
        this.radix = radix;
    }

    @Override
    public boolean isEmpty(SerializerProvider prov, Object value) {
        return false;
    }

    @Override
    public void serialize(Object value, JsonGenerator gen, SerializerProvider provider)
            throws IOException
    {
        if (radix < Character.MIN_RADIX || radix > Character.MAX_RADIX) {
            String errorMsg = String.format("To use a custom radix for string serialization, use radix within [%d, %d]", Character.MIN_RADIX, Character.MAX_RADIX);
            provider.reportBadDefinition(handledType(), errorMsg);
        }

        String text = "";
        if (value instanceof BigInteger) {
            BigInteger bigIntegerValue = (BigInteger) value;
            text = bigIntegerValue.toString(radix);
        } else if (value instanceof Byte
                || value instanceof Short
                || value instanceof Integer
                || value instanceof Long) {
            long longValue = ((Number) value).longValue();
            text = Long.toString(longValue, radix);
        } else {
            provider.reportBadDefinition(handledType(),
                    "Trying to serialize a non-whole number with NumberToStringWithRadixSerializer");
        }

        gen.writeString(text);

    }

    @Override
    public String valueToString(Object value) {
        // should never be called
        throw new IllegalStateException();
    }
}
